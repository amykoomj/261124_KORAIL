"""앱 설정. 환경 변수(.env)에서 값을 읽고, 없으면 기본값을 쓴다."""
import os

from dotenv import load_dotenv

# 프로젝트 루트 (sales-analysis/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # 아래 Config가 읽기 전에 .env 반영


def _abs(path):
    """상대 경로는 프로젝트 루트 기준으로 바꾼다."""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    DATABASE = _abs(os.environ.get("DATABASE", os.path.join("instance", "sales.db")))
    # 값이 있으면 SQLite 대신 PostgreSQL(Supabase) 사용 — Vercel 배포용
    DATABASE_URL = os.environ.get("DATABASE_URL") or None
    # Vercel은 파일 시스템에 쓸 수 없으므로 로그를 표준 출력(Vercel 로그)으로 보낸다
    LOG_TO_STDOUT = bool(os.environ.get("VERCEL") or os.environ.get("LOG_TO_STDOUT"))
    # 업로드(CSV 파일 포함) 요청 최대 크기 — 기본 1MB
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 1024 * 1024))
    LOG_DIR = _abs(os.environ.get("LOG_DIR", "logs"))
    # CSV 일괄 입력 1회 최대 행 수
    CSV_MAX_ROWS = 5000
    # 되돌리기 스냅샷 보관 개수
    SNAPSHOT_KEEP = 10
    JSON_SORT_KEYS = False
