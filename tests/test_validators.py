import pytest

from app.validators import ValidationError, normalize_quarter, parse_id_list, to_int, validate_row


@pytest.mark.parametrize("raw", ["2026q1", "2026-1", "2026.Q1", "2026Q1", " 2026 - Q1 ", "2026/1", "2026-Q1"])
def test_quarter_normalize(raw):
    assert normalize_quarter(raw) == "2026-Q1"


@pytest.mark.parametrize("raw", ["2026-Q5", "26-Q1", "2026", "Q1", ""])
def test_quarter_invalid(raw):
    with pytest.raises(ValidationError) as e:
        validate_row({"quarter": raw, "branch": "서울", "amount": 1, "customers": 1})
    assert e.value.field == "quarter"


def test_to_int():
    assert to_int("1,250,000원") == 1250000
    assert to_int("4,200 명") == 4200
    assert to_int(15) == 15
    assert to_int("-5") is None
    assert to_int("abc") is None
    assert to_int("1.5") is None
    assert to_int(True) is None


@pytest.mark.parametrize("field,value", [("amount", "-5"), ("amount", "abc"),
                                         ("customers", "0"), ("customers", "abc")])
def test_number_invalid(field, value):
    row = {"quarter": "2026-Q1", "branch": "서울", "amount": "100", "customers": "10", field: value}
    with pytest.raises(ValidationError) as e:
        validate_row(row)
    assert e.value.field == field


def test_branch_rules():
    ok = validate_row({"quarter": "2026q1", "branch": "  서울  ", "amount": "1,000원", "customers": "3명"})
    assert ok == {"quarter": "2026-Q1", "branch": "서울", "amount": 1000, "customers": 3}
    for bad in ["", "   ", "가" * 31]:
        with pytest.raises(ValidationError) as e:
            validate_row({"quarter": "2026-Q1", "branch": bad, "amount": 1, "customers": 1})
        assert e.value.field == "branch"
    assert validate_row({"quarter": "2026-Q1", "branch": "가" * 30, "amount": 0, "customers": 1})["amount"] == 0


def test_parse_id_list():
    assert parse_id_list(None) is None
    assert parse_id_list("") == []
    assert parse_id_list("1,3") == [1, 3]
    with pytest.raises(ValidationError):
        parse_id_list("1,x")
