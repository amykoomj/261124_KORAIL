def ids(client, *names):
    bs = {b["name"]: b["id"] for b in client.get("/api/branches").get_json()}
    return ",".join(str(bs[n]) for n in names)


def test_summary_all(client):
    s = client.get("/api/summary").get_json()
    assert s["total_amount"] == 3_709_500_000
    assert s["total_customers"] == 140_400
    assert s["avg_arpu"] == 26421  # 3,709,500,000 / 140,400 = 26,420.94
    assert s["top_branch"] == {"name": "서울", "amount": 1_777_500_000}
    # Q4 978.6M vs Q3 973.1M → +0.57%
    assert s["qoq"] == {"from": "2026-Q3", "to": "2026-Q4", "rate": 0.6}
    assert s["count"] == 12 and s["branch_count"] == 3


def test_summary_quarter_filter(client):
    s = client.get("/api/summary?quarter=2026-Q2").get_json()
    assert s["total_amount"] == 438_500_000 + 192_700_000 + 259_300_000
    # Q2 890.5M vs Q1 867.3M
    assert s["qoq"]["from"] == "2026-Q1" and s["qoq"]["rate"] == round((890.5 - 867.3) / 867.3 * 100, 1)
    assert client.get("/api/summary?quarter=2026-Q1").get_json()["qoq"] is None


def test_summary_branch_filter(client):
    s = client.get("/api/summary?branches=" + ids(client, "부산")).get_json()
    assert s["total_amount"] == 1_117_000_000
    assert s["top_branch"]["name"] == "부산"
    # 부산 Q4 301.2M vs Q3 287.6M
    assert s["qoq"]["rate"] == round((301.2 - 287.6) / 287.6 * 100, 1)


def test_summary_empty(empty_client):
    s = empty_client.get("/api/summary").get_json()
    assert s["total_amount"] == 0 and s["avg_arpu"] is None and s["top_branch"] is None and s["qoq"] is None
    s = empty_client.get("/api/summary?branches=").get_json()
    assert s["count"] == 0


def test_chart_data(client):
    c = client.get("/api/chart-data").get_json()
    assert c["quarters"] == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert [s["branch"] for s in c["series"]] == ["서울", "대전", "부산"]
    assert c["series"][0]["amount"][0] == 412_000_000
    assert c["bar"]["quarter"] == "2026-Q4"
    assert c["donut"]["scope"] == "전체 분기"
    assert {i["branch"]: i["customers"] for i in c["donut"]["items"]}["서울"] == 64200

    c = client.get("/api/chart-data?bar_quarter=2026-Q2&quarter=2026-Q1").get_json()
    assert c["bar"]["quarter"] == "2026-Q2" and c["donut"]["scope"] == "2026-Q1"


def test_chart_gaps_are_null(client):
    client.post("/api/sales", json={"quarter": "2026-Q2", "branch": "광주", "amount": 10, "customers": 1})
    c = client.get("/api/chart-data").get_json()
    gj = next(s for s in c["series"] if s["branch"] == "광주")
    assert gj["amount"] == [None, 10, None, None]
