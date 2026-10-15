from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import smtplib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from . import config

_ph = PasswordHasher()   # Argon2id, tham số mặc định của thư viện
# Băm giả để thời gian phản hồi khi email không tồn tại gần với khi sai mật khẩu (chống dò tài khoản)
_DUMMY_HASH = _ph.hash("not-a-real-password")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, pw) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(pw: str, email: str = "") -> str | None:
    """Trả về thông báo lỗi nếu mật khẩu không đạt chính sách, ngược lại None."""
    if len(pw) < config.PASSWORD_MIN_LEN:
        return f"Mật khẩu phải có ít nhất {config.PASSWORD_MIN_LEN} ký tự."
    if len(pw) > 128:
        return "Mật khẩu quá dài (tối đa 128 ký tự)."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Mật khẩu phải gồm cả chữ và số."
    if email and pw.lower() == email.lower():
        return "Mật khẩu không được trùng email."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite trả về datetime không có múi giờ; coi là UTC để so sánh an toàn."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class RateLimiter:
    """Cửa sổ trượt trong bộ nhớ. Đủ cho demo một instance; nhiều instance cần Redis hoặc bảng DB."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, limit: int, window_s: int) -> bool:
        """Ghi một lượt; trả False nếu vượt giới hạn."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def send_email(to: str, subject: str, body: str) -> bool:
    """Gửi email qua SMTP. Trả False nếu chưa cấu hình hoặc gửi lỗi (không ném lỗi, không ghi nội dung)."""
    if not config.SMTP_CONFIGURED:
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception:  # noqa: BLE001
        return False


def expires_in(**kw) -> datetime:
    return utcnow() + timedelta(**kw)
