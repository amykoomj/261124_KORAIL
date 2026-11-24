"""/api/* JSON API 블루프린트."""
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request

from . import services
from .db import get_db
from .services import ConflictError, NotFoundError, audit
from .validators import ValidationError, parse_id_list, validate_quarter, validate_row

bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------- 공통

def fail(message, status=400, field=None):
    body = {"ok": False, "error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


@bp.errorhandler(ValidationError)
def _validation(e):
    return fail(e.message, 400, e.field)


@bp.errorhandler(ConflictError)
def _conflict(e):
    return fail(e.message, 409)


@bp.errorhandler(NotFoundError)
def _not_found(e):
    return fail(e.message, 404)


def _keep():
    return current_app.config["SNAPSHOT_KEEP"]


def _filters():
    """쿼리스트링의 quarter / branches 필터를 읽는다."""
    q = request.args.get("quarter", "").strip()
    quarter = validate_quarter(q) if q and q != "all" else None
    branch_ids = parse_id_list(request.args.get("branches"))
    return quarter, branch_ids


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("요청 형식이 올바르지 않습니다 (JSON 필요)")
    return data


# ---------------------------------------------------------------- 조회

@bp.get("/branches")
def branches():
    return jsonify(services.list_branches(get_db()))


@bp.get("/quarters")
def quarters():
    return jsonify(services.list_quarters(get_db()))


@bp.get("/sales")
def sales_list():
    quarter, branch_ids = _filters()
    direction = "desc" if request.args.get("dir") == "desc" else "asc"
    return jsonify(services.list_sales(get_db(), quarter, branch_ids, request.args.get("sort"), direction))


@bp.get("/summary")
def summary():
    quarter, branch_ids = _filters()
    return jsonify(services.summary(get_db(), quarter, branch_ids))


@bp.get("/chart-data")
def chart_data():
    quarter, branch_ids = _filters()
    bq = request.args.get("bar_quarter", "").strip() or None
    return jsonify(services.chart_data(get_db(), branch_ids, bq, quarter))


@bp.get("/status")
def status():
    return jsonify(services.status(get_db()))


# ---------------------------------------------------------------- 쓰기

@bp.post("/sales")
def sales_add():
    row = validate_row(_json_body())
    db = get_db()
    with db:
        action, sale_id = services.upsert(db, row)
    audit.info("%s quarter=%s branch=%s amount=%s customers=%s id=%s",
               "ADD" if action == "add" else "UPDATE(upsert)",
               row["quarter"], row["branch"], row["amount"], row["customers"], sale_id)
    return jsonify({"ok": True, "row": services.get_sale(db, sale_id), "action": action}), (
        201 if action == "add" else 200
    )


@bp.put("/sales/<int:sale_id>")
def sales_update(sale_id):
    row = validate_row(_json_body())
    db = get_db()
    with db:
        services.update_sale(db, sale_id, row)
    audit.info("UPDATE id=%s quarter=%s branch=%s amount=%s customers=%s",
               sale_id, row["quarter"], row["branch"], row["amount"], row["customers"])
    return jsonify({"ok": True, "row": services.get_sale(db, sale_id)})


@bp.delete("/sales/<int:sale_id>")
def sales_delete(sale_id):
    db = get_db()
    with db:
        row = services.delete_sale(db, sale_id, _keep())
    audit.info("DELETE id=%s quarter=%s branch=%s", sale_id, row["quarter"], row["branch"])
    return jsonify({"ok": True})


@bp.post("/sales/import")
def sales_import():
    if "file" in request.files:
        f = request.files["file"]
        raw = f.read()
        if not raw:
            raise ValidationError("빈 파일입니다.", "file")
        for enc in ("utf-8-sig", "cp949"):  # 엑셀에서 저장한 CSV(cp949)도 받는다
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValidationError("파일 인코딩을 읽을 수 없습니다. UTF-8 CSV로 저장해 주세요.", "file")
        source = f"file:{f.filename}"
    else:
        data = request.get_json(silent=True) or {}
        text = str(data.get("csv") or request.form.get("csv") or "")
        source = "text"

    db = get_db()
    with db:
        result = services.import_csv(db, text, current_app.config["CSV_MAX_ROWS"], _keep())
    audit.info("IMPORT source=%s added=%s updated=%s skipped=%s",
               source, result["added"], result["updated"], len(result["skipped"]))
    return jsonify({"ok": True, **result})


@bp.delete("/sales/sample")
def sales_clear_sample():
    db = get_db()
    with db:
        n = services.clear_sample(db, _keep())
    audit.info("CLEAR_SAMPLE deleted=%s", n)
    return jsonify({"ok": True, "deleted": n})


@bp.post("/reset")
def reset():
    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "RESET":
        return fail("초기화하려면 확인 값(RESET)이 필요합니다.", 400, "confirm")
    db = get_db()
    with db:
        services.reset_all(db, _keep())
    audit.info("RESET all data")
    return jsonify({"ok": True})


@bp.post("/undo")
def undo():
    db = get_db()
    with db:
        action = services.undo(db)
    if action is None:
        return fail("되돌릴 작업이 없습니다.", 404)
    audit.info("UNDO action=%s", action)
    return jsonify({"ok": True, "action": action})


# ---------------------------------------------------------------- 내보내기

def _export_rows():
    quarter, branch_ids = _filters()
    return services.list_sales(get_db(), quarter, branch_ids)


def _filename(ext):
    return f"sales_{datetime.now():%Y%m%d_%H%M}.{ext}"


@bp.get("/export.csv")
def export_csv():
    body = services.export_csv(_export_rows())
    return Response(body, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{_filename("csv")}"'})


@bp.get("/export.xlsx")
def export_xlsx():
    body = services.export_xlsx(_export_rows())
    return Response(
        body,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_filename("xlsx")}"'},
    )
