"""비즈니스 로직: upsert, 조회, 요약 계산, 스냅샷/되돌리기, CSV 파싱, 내보내기.

함수들은 sqlite3 연결(db)을 받는다. 쓰기 함수는 호출하는 쪽에서 `with db:`로 트랜잭션을 묶는다.
"""
import csv
import io
import json
import logging
import math

from .validators import ValidationError, validate_row

PALETTE_SIZE = 8
audit = logging.getLogger("sales.audit")

_SALE_COLS = "s.id, s.quarter, s.branch_id, b.name AS branch, s.amount, s.customers, s.is_sample"


class ConflictError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def rnd(x):
    """사사오입 반올림 (파이썬 round는 짝수 반올림이라 쓰지 않음)."""
    return int(math.floor(x + 0.5))


def _row_dict(r):
    d = dict(r)
    d["is_sample"] = bool(d["is_sample"])
    d["arpu"] = rnd(d["amount"] / d["customers"]) if d["customers"] else None
    return d


# ---------------------------------------------------------------- 지점
def list_branches(db):
    return db.all("SELECT id, name, color_index FROM branches ORDER BY id")


def _next_color(db):
    """비어 있는 가장 앞 색 번호. 8개를 모두 쓰면 7번을 함께 쓴다."""
    used = {r["color_index"] for r in db.all("SELECT color_index FROM branches")}
    for i in range(PALETTE_SIZE):
        if i not in used:
            return i
    return PALETTE_SIZE - 1


def get_or_create_branch(db, name):
    r = db.one("SELECT id FROM branches WHERE name = ?", (name,))
    if r:
        return r["id"]
    return db.scalar(
        "INSERT INTO branches (name, color_index) VALUES (?, ?) RETURNING id",
        (name, _next_color(db)),
    )


def cleanup_branches(db):
    """매출 데이터가 하나도 없는 지점을 지워 색 번호를 반환한다."""
    db.execute("DELETE FROM branches WHERE id NOT IN (SELECT DISTINCT branch_id FROM sales)")


# ---------------------------------------------------------------- 조회

def list_quarters(db):
    return [r["quarter"] for r in db.all("SELECT DISTINCT quarter FROM sales ORDER BY quarter")]


def _where(quarter=None, branch_ids=None):
    cond, args = [], []
    if quarter:
        cond.append("s.quarter = ?")
        args.append(quarter)
    if branch_ids is not None:
        if not branch_ids:
            cond.append("1 = 0")  # 선택한 지점 없음
        else:
            cond.append(f"s.branch_id IN ({','.join('?' * len(branch_ids))})")
            args.extend(branch_ids)
    return (" WHERE " + " AND ".join(cond)) if cond else "", args


SORT_KEYS = {"quarter", "branch", "amount", "customers", "arpu"}


def list_sales(db, quarter=None, branch_ids=None, sort=None, direction="asc"):
    where, args = _where(quarter, branch_ids)
    rows = db.all(
        f"SELECT {_SALE_COLS} FROM sales s JOIN branches b ON b.id = s.branch_id{where}"
        " ORDER BY s.quarter, b.id",
        args,
    )
    out = [_row_dict(r) for r in rows]
    if sort in SORT_KEYS:
        out.sort(key=lambda d: (d[sort], d["branch"]), reverse=(direction == "desc"))
    return out


def get_sale(db, sale_id):
    r = db.one(
        f"SELECT {_SALE_COLS} FROM sales s JOIN branches b ON b.id = s.branch_id WHERE s.id = ?",
        (sale_id,),
    )
    return _row_dict(r) if r else None


def status(db):
    return {
        "sample_count": db.scalar("SELECT COUNT(*) AS n FROM sales WHERE is_sample = 1"),
        "undo_count": db.scalar("SELECT COUNT(*) AS n FROM snapshots"),
        "total_count": db.scalar("SELECT COUNT(*) AS n FROM sales"),
    }


# ---------------------------------------------------------------- 쓰기

def upsert(db, row, is_sample=0):
    """같은 분기+지점이 있으면 값을 갱신, 없으면 추가. ('add'|'update', id) 반환."""
    branch_id = get_or_create_branch(db, row["branch"])
    existed = db.one(
        "SELECT id FROM sales WHERE quarter = ? AND branch_id = ?", (row["quarter"], branch_id)
    )
    sale_id = db.scalar(
        "INSERT INTO sales (quarter, branch_id, amount, customers, is_sample) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(quarter, branch_id) DO UPDATE SET amount = excluded.amount,"
        " customers = excluded.customers, is_sample = excluded.is_sample,"
        f" updated_at = {db.now} RETURNING id",
        (row["quarter"], branch_id, row["amount"], row["customers"], is_sample),
    )
    return ("update" if existed else "add"), sale_id


def update_sale(db, sale_id, row):
    if not get_sale(db, sale_id):
        raise NotFoundError("해당 데이터를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.")
    clash = db.one(
        "SELECT s.id FROM sales s JOIN branches b ON b.id = s.branch_id"
        " WHERE s.quarter = ? AND b.name = ? AND s.id <> ?",
        (row["quarter"], row["branch"], sale_id),
    )
    if clash:
        raise ConflictError(f"{row['quarter']} {row['branch']} 데이터가 이미 있습니다.")
    branch_id = get_or_create_branch(db, row["branch"])
    db.execute(
        "UPDATE sales SET quarter = ?, branch_id = ?, amount = ?, customers = ?, is_sample = 0,"
        f" updated_at = {db.now} WHERE id = ?",
        (row["quarter"], branch_id, row["amount"], row["customers"], sale_id),
    )
    cleanup_branches(db)  # 지점명을 바꿔 옛 지점이 비었을 수 있음


def delete_sale(db, sale_id, keep=10):
    row = get_sale(db, sale_id)
    if not row:
        raise NotFoundError("해당 데이터를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.")
    take_snapshot(db, "delete", keep)
    db.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
    cleanup_branches(db)
    return row


def clear_sample(db, keep=10):
    n = db.scalar("SELECT COUNT(*) AS n FROM sales WHERE is_sample = 1")
    if n:
        take_snapshot(db, "clear_sample", keep)
        db.execute("DELETE FROM sales WHERE is_sample = 1")
        cleanup_branches(db)
    return n


def reset_all(db, keep=10):
    take_snapshot(db, "reset", keep)
    db.execute("DELETE FROM sales")
    db.execute("DELETE FROM branches")


# ---------------------------------------------------------------- 스냅샷 / 되돌리기

def take_snapshot(db, action, keep=10):
    payload = {
        "branches": db.all("SELECT * FROM branches ORDER BY id"),
        "sales": db.all("SELECT * FROM sales ORDER BY id"),
    }
    db.execute(
        "INSERT INTO snapshots (action, payload) VALUES (?, ?)",
        (action, json.dumps(payload, ensure_ascii=False, default=str)),
    )
    db.execute(
        "DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT ?)",
        (keep,),
    )


def undo(db):
    """가장 최근 스냅샷으로 되돌린다. 스냅샷이 없으면 None."""
    snap = db.one("SELECT id, action, payload FROM snapshots ORDER BY id DESC LIMIT 1")
    if not snap:
        return None
    data = json.loads(snap["payload"])
    db.execute("DELETE FROM sales")
    db.execute("DELETE FROM branches")
    for b in data["branches"]:
        db.execute(
            "INSERT INTO branches (id, name, color_index, created_at) VALUES (?, ?, ?, ?)",
            (b["id"], b["name"], b["color_index"], b["created_at"]),
        )
    for s in data["sales"]:
        db.execute(
            "INSERT INTO sales (id, quarter, branch_id, amount, customers, is_sample, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (s["id"], s["quarter"], s["branch_id"], s["amount"], s["customers"],
             s["is_sample"], s["created_at"], s["updated_at"]),
        )
    db.reset_sequences("branches", "sales")
    db.execute("DELETE FROM snapshots WHERE id = ?", (snap["id"],))
    return snap["action"]


# ---------------------------------------------------------------- CSV 일괄 입력

def _split_line(line):
    if "\t" in line:
        parts = line.split("\t")
    else:
        parts = next(csv.reader([line]))
    return [p.strip().strip('"').strip() for p in parts]


def parse_csv(text, max_rows=5000):
    """CSV/TSV 텍스트 → (좋은 행 목록[(줄번호, row)], 건너뛴 행[{line, error}])."""
    lines = [(i + 1, l.strip()) for i, l in enumerate(text.splitlines())]
    lines = [(n, l) for n, l in lines if l]
    if not lines:
        raise ValidationError("붙여넣은 내용이 없습니다.", "csv")
    first = _split_line(lines[0][1])
    if first and ("분기" in first[0] or "quarter" in first[0].lower()):
        lines = lines[1:]  # 제목 줄
    if len(lines) > max_rows:
        raise ValidationError(f"한 번에 {max_rows:,}행까지만 입력할 수 있습니다.", "csv")

    good, skipped = [], []
    for n, line in lines:
        p = _split_line(line)
        if len(p) < 4:
            skipped.append({"line": n, "error": "항목이 4개가 아닙니다"})
            continue
        try:
            # 고객 수 칸 뒤에 따옴표 없는 쉼표가 있으면(예: 4,200) 이어 붙인다 — 아티팩트와 동일
            row = validate_row({"quarter": p[0], "branch": p[1], "amount": p[2],
                                "customers": "".join(p[3:])})
        except ValidationError as e:
            skipped.append({"line": n, "error": e.message})
            continue
        good.append((n, row))
    return good, skipped


def import_csv(db, text, max_rows=5000, keep=10):
    good, skipped = parse_csv(text, max_rows)
    added = updated = 0
    if good:
        take_snapshot(db, "import", keep)
        for _, row in good:
            action, _ = upsert(db, row)
            if action == "add":
                added += 1
            else:
                updated += 1
    return {"added": added, "updated": updated, "skipped": skipped}


# ---------------------------------------------------------------- 요약 / 그래프

def summary(db, quarter=None, branch_ids=None):
    rows = list_sales(db, None, branch_ids)  # 지점 필터만 적용한 전체 분기
    scoped = [r for r in rows if not quarter or r["quarter"] == quarter]

    total_amount = sum(r["amount"] for r in scoped)
    total_customers = sum(r["customers"] for r in scoped)
    by_branch = {}
    for r in scoped:
        by_branch[r["branch"]] = by_branch.get(r["branch"], 0) + r["amount"]
    top = max(by_branch.items(), key=lambda x: x[1]) if by_branch else None

    qs = sorted({r["quarter"] for r in rows})
    cur = quarter or (qs[-1] if qs else None)
    qoq = None
    if cur in qs and qs.index(cur) > 0:
        prev = qs[qs.index(cur) - 1]
        a_cur = sum(r["amount"] for r in rows if r["quarter"] == cur)
        a_prev = sum(r["amount"] for r in rows if r["quarter"] == prev)
        if a_prev > 0:
            qoq = {"from": prev, "to": cur, "rate": round((a_cur - a_prev) / a_prev * 100, 1)}

    return {
        "total_amount": total_amount,
        "total_customers": total_customers,
        "avg_arpu": rnd(total_amount / total_customers) if total_customers else None,
        "top_branch": {"name": top[0], "amount": top[1]} if top else None,
        "qoq": qoq,
        "count": len(scoped),
        "branch_count": len(by_branch),
    }


def chart_data(db, branch_ids=None, bar_quarter=None, quarter=None):
    rows = list_sales(db, None, branch_ids)
    quarters = sorted({r["quarter"] for r in rows})
    branches = [b for b in list_branches(db)
                if (branch_ids is None or b["id"] in branch_ids)
                and any(r["branch_id"] == b["id"] for r in rows)]
    cell = {(r["quarter"], r["branch_id"]): r for r in rows}

    series = []
    for b in branches:
        cells = [cell.get((q, b["id"])) for q in quarters]
        series.append({
            "branch": b["name"], "branch_id": b["id"], "color_index": b["color_index"],
            "amount": [c["amount"] if c else None for c in cells],
            "arpu": [c["amount"] / c["customers"] if c else None for c in cells],
        })

    if bar_quarter not in quarters:
        bar_quarter = quarters[-1] if quarters else None
    bar_items = [
        {"branch": b["name"], "color_index": b["color_index"],
         "amount": cell[(bar_quarter, b["id"])]["amount"]}
        for b in branches if (bar_quarter, b["id"]) in cell
    ]

    donut_items = []
    for b in branches:
        c = sum(r["customers"] for r in rows
                if r["branch_id"] == b["id"] and (not quarter or r["quarter"] == quarter))
        if c > 0:
            donut_items.append({"branch": b["name"], "color_index": b["color_index"], "customers": c})

    return {
        "quarters": quarters,
        "series": series,
        "bar": {"quarter": bar_quarter, "items": bar_items},
        "donut": {"scope": quarter or "전체 분기", "items": donut_items},
    }


# ---------------------------------------------------------------- 내보내기

EXPORT_HEADER = ["분기", "지점", "매출 금액", "고객 수"]


def export_csv(rows):
    """UTF-8 BOM CSV. 4열(분기,지점,금액,고객수)이라 그대로 다시 일괄 입력할 수 있다."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(EXPORT_HEADER)
    for r in rows:
        w.writerow([r["quarter"], r["branch"], r["amount"], r["customers"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_xlsx(rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "매출"
    ws.append(EXPORT_HEADER + ["객단가"])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEEF8")
        c.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append([r["quarter"], r["branch"], r["amount"], r["customers"], r["arpu"]])
    A = sum(r["amount"] for r in rows)
    C = sum(r["customers"] for r in rows)
    ws.append([f"합계 ({len(rows)}건)", "", A, C, rnd(A / C) if C else None])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=5):
        for c in row:
            c.number_format = "#,##0"
    for col, width in zip("ABCDE", (12, 16, 18, 12, 12)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
