"""`python run.py` 로 실행. DB 파일이 없으면 테이블을 만들고 예시 데이터를 넣는다."""
import os

from app import create_app
from app.config import Config

is_new = not os.path.exists(Config.DATABASE)
app = create_app()  # DB 파일이 없으면 여기서 init-db 수행

if is_new:
    from app.db import get_db
    from app.seed import seed

    with app.app_context():
        n = seed(get_db())
    print(f"새 DB를 만들고 예시 데이터 {n}건을 넣었습니다: {Config.DATABASE}")

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    print(f"브라우저에서 http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port} 을 여세요.")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
