"""DB 연결 관리와 init-db / seed CLI 명령.

- 로컬: SQLite (DATABASE 경로)
- 배포(Vercel): DATABASE_URL이 있으면 PostgreSQL(Supabase)

두 DB를 같은 코드로 쓰도록 얇은 래퍼(Database)를 둔다. SQL은 `?` 자리표시자로 쓰고,
Postgres에서는 `%s`로 바꿔 실행한다. 행은 항상 dict로 돌려준다.
"""
import os
import sqlite3

import click
from flask import current_app, g

SQLITE_NOW = "datetime('now','localtime')"
PG_NOW = "to_char(now() at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')"


def _dict_factory(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


class Database:
    def __init__(self, url=None, path=None):
        self.pg = bool(url)
        if self.pg:
            import psycopg2
            import psycopg2.extras

            self.conn = psycopg2.connect(
                url, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=10
            )
        else:
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = _dict_factory
            # SQLite는 외래키 검사가 기본 OFF — 연결마다 켠다
            self.conn.execute("PRAGMA foreign_keys = ON")
        self.now = PG_NOW if self.pg else SQLITE_NOW

    # ---- 실행 ----
    def execute(self, sql, args=()):
        if self.pg:
            cur = self.conn.cursor()
            cur.execute(sql.replace("?", "%s"), tuple(args))
            return cur
        return self.conn.execute(sql, tuple(args))

    def all(self, sql, args=()):
        return [dict(r) for r in self.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.execute(sql, args).fetchone()
        return dict(r) if r is not None else None

    def scalar(self, sql, args=()):
        r = self.one(sql, args)
        return next(iter(r.values())) if r else None

    def reset_sequences(self, *tables):
        """id를 직접 넣은 뒤(되돌리기) Postgres 시퀀스를 최댓값 다음으로 맞춘다."""
        if not self.pg:
            return
        for t in tables:
            self.execute(
                f"SELECT setval(pg_get_serial_sequence('{t}', 'id'),"
                f" COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"
            )

    # ---- 트랜잭션: with db: ... ----
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        return False

    def close(self):
        self.conn.close()


def open_db(config):
    return Database(url=config.get("DATABASE_URL"), path=config["DATABASE"])


def get_db():
    """요청 단위로 하나의 연결을 열어 재사용한다."""
    if "db" not in g:
        g.db = open_db(current_app.config)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path=None):
    """(SQLite) schema.sql로 테이블을 (다시) 만든다. 기존 데이터는 지워진다."""
    path = path or current_app.config["DATABASE"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        with current_app.open_resource("schema.sql") as f:
            conn.executescript(f.read().decode("utf-8"))
        conn.commit()
    finally:
        conn.close()


def ensure_db(app):
    """SQLite DB 파일이 없으면 자동으로 만든다. 새로 만들었으면 True. (Postgres는 해당 없음)"""
    if app.config.get("DATABASE_URL"):
        return False
    path = app.config["DATABASE"]
    if os.path.exists(path):
        return False
    with app.app_context():
        init_db(path)
    return True


@click.command("init-db")
def init_db_command():
    """테이블을 새로 만든다 (기존 데이터 삭제)."""
    if current_app.config.get("DATABASE_URL"):
        raise click.ClickException(
            "Postgres(Supabase) 테이블은 `supabase db push`로 만듭니다 (supabase/migrations 참고)."
        )
    init_db()
    click.echo(f"DB를 초기화했습니다: {current_app.config['DATABASE']}")


@click.command("seed")
def seed_command():
    """예시 데이터(서울·대전·부산 × 2026 Q1~Q4)를 넣는다."""
    from .seed import seed

    n = seed(get_db())
    click.echo(f"예시 데이터 {n}건을 입력했습니다.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)
