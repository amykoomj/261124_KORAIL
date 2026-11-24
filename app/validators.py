"""입력값 정규화·검증. 클라이언트(app.js)의 규칙과 같게 유지한다."""
import re

QUARTER_RE = re.compile(r"^\d{4}-Q[1-4]$")
_QUARTER_LOOSE = re.compile(r"^(\d{4})[-./]?Q?([1-4])Q?$")
_NUM_STRIP = re.compile(r"[,\s원명]")
BRANCH_MAX = 30
AMOUNT_MAX = 10**15  # 1,000조 원 — 비정상 입력 차단용 상한


class ValidationError(ValueError):
    """사용자에게 보여줄 한글 메시지와 문제 필드를 담는다."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def normalize_quarter(value):
    """'2026q1', '2026-1', '2026.Q1', '2026 Q1' → '2026-Q1'. 형식이 안 맞으면 정리만 한 값을 돌려준다."""
    s = re.sub(r"\s+", "", str(value if value is not None else "")).upper()
    m = _QUARTER_LOOSE.match(s)
    return f"{m.group(1)}-Q{m.group(2)}" if m else s


def to_int(value):
    """'1,250,000원', '4,200명' → 정수. 정수가 아니면 None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    s = _NUM_STRIP.sub("", str(value))
    return int(s) if re.fullmatch(r"\d+", s) else None


def validate_quarter(value):
    q = normalize_quarter(value)
    if not QUARTER_RE.match(q):
        raise ValidationError("분기는 2026-Q1 형식으로 입력하세요", "quarter")
    return q


def validate_branch(value):
    b = str(value if value is not None else "").strip()
    if not b:
        raise ValidationError("지점명을 입력하세요", "branch")
    if len(b) > BRANCH_MAX:
        raise ValidationError(f"지점명은 {BRANCH_MAX}자 이내로 입력하세요", "branch")
    return b


def validate_row(data):
    """{quarter, branch, amount, customers} 검증 후 정규화된 dict 반환. 첫 오류에서 ValidationError."""
    if not isinstance(data, dict):
        raise ValidationError("요청 형식이 올바르지 않습니다")
    q = validate_quarter(data.get("quarter"))
    b = validate_branch(data.get("branch"))

    a = to_int(data.get("amount"))
    if a is None or a < 0:
        raise ValidationError("매출 금액은 0 이상의 숫자만 입력하세요", "amount")
    if a > AMOUNT_MAX:
        raise ValidationError("매출 금액이 너무 큽니다", "amount")

    c = to_int(data.get("customers"))
    if c is None:
        raise ValidationError("고객 수는 숫자만 입력하세요", "customers")
    if c < 1:
        raise ValidationError("고객 수는 1 이상이어야 합니다", "customers")
    if c > AMOUNT_MAX:
        raise ValidationError("고객 수가 너무 큽니다", "customers")

    return {"quarter": q, "branch": b, "amount": a, "customers": c}


def parse_id_list(value):
    """'1,3' → [1, 3]. None이면 None(=전체), 빈 문자열이면 [](=선택 없음)."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return []
    try:
        return [int(x) for x in value.split(",") if x.strip()]
    except ValueError:
        raise ValidationError("지점 필터 값이 올바르지 않습니다", "branches")
