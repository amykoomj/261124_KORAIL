import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "DATABASE_URL": None,  # 테스트는 항상 임시 SQLite
        "LOG_TO_STDOUT": False,
        "LOG_DIR": str(tmp_path / "logs"),
    })
    yield app


@pytest.fixture
def seeded(app):
    with app.app_context():
        seed(get_db())
    return app


@pytest.fixture
def client(seeded):
    return seeded.test_client()


@pytest.fixture
def empty_client(app):
    return app.test_client()
