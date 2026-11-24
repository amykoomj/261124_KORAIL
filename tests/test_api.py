import io
import os

from openpyxl import load_workbook

NEW = {"quarter": "2027-Q1", "branch": "광주", "amount": "120,000,000원", "customers": "4,000"}


def count(client):
    return len(client.get("/api/sales").get_json())


def test_index_and_404(client):
    assert client.get("/").status_code == 200
    r = client.get("/no-such-page")
    assert r.status_code == 404 and "찾을 수 없습니다" in r.get_data(as_text=True)
    r = client.get("/api/no-such")
    assert r.status_code == 404 and r.get_json()["ok"] is False


def test_list_and_lookups(client):
    assert count(client) == 12
    assert client.get("/api/quarters").get_json() == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    bs = client.get("/api/branches").get_json()
    assert [(b["name"], b["color_index"]) for b in bs] == [("서울", 0), ("대전", 1), ("부산", 2)]
    rows = client.get("/api/sales?quarter=2026-Q1&sort=amount&dir=desc").get_json()
    assert [r["branch"] for r in rows] == ["서울", "부산", "대전"]
    assert rows[0]["arpu"] == round(412000000 / 15200)


def test_add_then_upsert(client):
    r = client.post("/api/sales", json=NEW)
    assert r.status_code == 201
    body = r.get_json()
    assert body["action"] == "add" and body["row"]["amount"] == 120_000_000
    assert count(client) == 13

    r = client.post("/api/sales", json={**NEW, "amount": 999})
    assert r.status_code == 200 and r.get_json()["action"] == "update"
    assert count(client) == 13
    assert r.get_json()["row"]["amount"] == 999


def test_server_validation(client):
    r = client.post("/api/sales", json={**NEW, "quarter": "2026-Q5"})
    assert r.status_code == 400
    j = r.get_json()
    assert j["ok"] is False and j["field"] == "quarter" and "형식" in j["error"]
    assert client.post("/api/sales", json={**NEW, "customers": 0}).status_code == 400
    assert client.post("/api/sales", data="not json").status_code == 400


def test_update_and_conflict(client):
    rows = client.get("/api/sales?quarter=2026-Q1").get_json()
    seoul = next(r for r in rows if r["branch"] == "서울")
    r = client.put(f"/api/sales/{seoul['id']}", json={"quarter": "2026-Q1", "branch": "서울",
                                                       "amount": 1, "customers": 1})
    assert r.status_code == 200 and r.get_json()["row"]["is_sample"] is False

    r = client.put(f"/api/sales/{seoul['id']}", json={"quarter": "2026-Q1", "branch": "부산",
                                                       "amount": 1, "customers": 1})
    assert r.status_code == 409
    assert client.put("/api/sales/99999", json={**NEW}).status_code == 404


def test_delete_and_undo(client):
    before = client.get("/api/sales").get_json()
    target = before[0]
    assert client.delete(f"/api/sales/{target['id']}").get_json()["ok"]
    assert count(client) == 11
    r = client.post("/api/undo")
    assert r.status_code == 200 and r.get_json()["action"] == "delete"
    assert client.get("/api/sales").get_json() == before
    assert client.post("/api/undo").status_code == 404


def test_csv_import(client):
    text = "분기,지점,금액,고객수\n2027-Q1,서울,100,10\n2027-Q2,서울,\"1,200\",10\n2027-Q5,서울,1,1\n" \
           "2027-Q3\t대구\t300\t30\n2027-Q4,서울,abc,1\n"
    r = client.post("/api/sales/import", json={"csv": text})
    j = r.get_json()
    assert j["ok"] and j["added"] == 3 and j["updated"] == 0
    assert [s["line"] for s in j["skipped"]] == [4, 6]
    assert count(client) == 15
    # 일괄 입력도 되돌릴 수 있다
    assert client.post("/api/undo").get_json()["action"] == "import"
    assert count(client) == 12


def test_csv_file_upload_cp949(client):
    data = {"file": (io.BytesIO("2027-Q1,울산,500,5\n".encode("cp949")), "a.csv")}
    j = client.post("/api/sales/import", data=data, content_type="multipart/form-data").get_json()
    assert j["added"] == 1
    assert any(b["name"] == "울산" for b in client.get("/api/branches").get_json())


def test_csv_empty_and_too_big(client):
    assert client.post("/api/sales/import", json={"csv": "  \n"}).status_code == 400
    big = {"file": (io.BytesIO(b"x" * (1024 * 1024 + 10)), "big.csv")}
    r = client.post("/api/sales/import", data=big, content_type="multipart/form-data")
    assert r.status_code == 413 and r.get_json()["ok"] is False


def test_clear_sample_keeps_user_rows(client):
    client.post("/api/sales", json=NEW)
    rows = client.get("/api/sales?quarter=2026-Q4").get_json()
    seoul = next(r for r in rows if r["branch"] == "서울")
    client.put(f"/api/sales/{seoul['id']}", json={"quarter": "2026-Q4", "branch": "서울",
                                                   "amount": 5, "customers": 5})
    r = client.delete("/api/sales/sample").get_json()
    assert r["deleted"] == 11
    left = client.get("/api/sales").get_json()
    assert {(x["quarter"], x["branch"]) for x in left} == {("2027-Q1", "광주"), ("2026-Q4", "서울")}


def test_reset(client):
    assert client.post("/api/reset", json={}).status_code == 400
    assert client.post("/api/reset", json={"confirm": "RESET"}).get_json()["ok"]
    assert count(client) == 0 and client.get("/api/branches").get_json() == []
    client.post("/api/undo")
    assert count(client) == 12


def test_branch_color_reuse(client):
    daejeon = next(b for b in client.get("/api/branches").get_json() if b["name"] == "대전")
    for r in client.get("/api/sales").get_json():
        if r["branch"] == "대전":
            client.delete(f"/api/sales/{r['id']}")
    client.post("/api/sales", json={"quarter": "2026-Q1", "branch": "인천", "amount": 1, "customers": 1})
    client.post("/api/sales", json={"quarter": "2026-Q1", "branch": "수원", "amount": 1, "customers": 1})
    colors = {b["name"]: b["color_index"] for b in client.get("/api/branches").get_json()}
    assert colors["서울"] == 0 and colors["부산"] == 2  # 기존 색 유지
    assert colors["인천"] == daejeon["color_index"] == 1  # 비어 있는 가장 앞 번호
    assert colors["수원"] == 3


def test_snapshots_keep_10(client, seeded):
    rows = client.get("/api/sales").get_json()
    for r in rows:
        client.delete(f"/api/sales/{r['id']}")
    assert client.get("/api/status").get_json()["undo_count"] == 10


def test_export_csv(client):
    r = client.get("/api/export.csv?quarter=2026-Q1")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert r.data.startswith(b"\xef\xbb\xbf")
    lines = r.data.decode("utf-8-sig").strip().splitlines()
    assert lines[0] == "분기,지점,매출 금액,고객 수" and len(lines) == 4


def test_export_xlsx(client):
    r = client.get("/api/export.xlsx")
    ws = load_workbook(io.BytesIO(r.data)).active
    assert ws["A1"].value == "분기"
    last = ws.max_row
    assert last == 14 and ws.cell(last, 1).value.startswith("합계")
    assert ws.cell(last, 3).value == 3_709_500_000
    assert ws.cell(2, 3).number_format == "#,##0"


def test_audit_log(client, seeded):
    client.post("/api/sales", json=NEW)
    client.post("/api/reset", json={"confirm": "RESET"})
    log = open(os.path.join(seeded.config["LOG_DIR"], "app.log"), encoding="utf-8").read()
    assert "ADD quarter=2027-Q1 branch=광주" in log and "RESET" in log
