"""Cấu hình đọc từ biến môi trường (hoặc file .env ở thư mục gốc, không commit). Không có bí mật nào nằm trong mã nguồn."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.is_file():
        return
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

APP_ENV = os.getenv("APP_ENV", "dev")           # dev | prod
IS_PROD = APP_ENV == "prod"


def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        (ROOT / "var").mkdir(exist_ok=True)
        return f"sqlite:///{(ROOT / 'var' / 'app.db').as_posix()}"
    # Neon/Render/Heroku thường cấp "postgres://" hoặc "postgresql://": đổi sang driver psycopg 3
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _db_url()

# Khóa dùng để băm token phiên / token đặt lại mật khẩu (HMAC). Bắt buộc và đủ mạnh ở production.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if IS_PROD:
        raise RuntimeError("Thiếu biến môi trường SECRET_KEY (tối thiểu 32 ký tự) ở môi trường production.")
    SECRET_KEY = secrets.token_urlsafe(48)       # dev: khóa tạm; khởi động lại thì phiên cũ mất hiệu lực
if IS_PROD and len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY phải có ít nhất 32 ký tự.")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", FRONTEND_URL).split(",") if o.strip()]
if IS_PROD and "*" in ALLOWED_ORIGINS:
    raise RuntimeError("ALLOWED_ORIGINS không được dùng '*' ở production.")

COOKIE_NAME = "ckd_session"
COOKIE_SECURE = IS_PROD
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))
INVITE_TOKEN_TTL_HOURS = int(os.getenv("INVITE_TOKEN_TTL_HOURS", "72"))

# Số lớp proxy tin cậy phía trước ứng dụng (0 = dùng địa chỉ kết nối trực tiếp, an toàn nhất).
# Vercel -> Render: đặt 2, khi đó IP khách là phần tử thứ 2 tính từ phải của X-Forwarded-For (các phần tử bên trái có thể bị giả).
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))

LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
PASSWORD_MIN_LEN = 10

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_CONFIGURED = bool(SMTP_HOST and SMTP_FROM)
