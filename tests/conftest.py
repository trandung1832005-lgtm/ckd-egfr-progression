"""Thiết lập môi trường kiểm thử cho backend đa người dùng: DB SQLite tạm, dựng bằng chính Alembic migration."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="ckd_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["APP_ENV"] = "dev"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"
os.environ.pop("SMTP_HOST", None)

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    yield
