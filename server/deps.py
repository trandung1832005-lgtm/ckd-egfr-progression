"""Phụ thuộc dùng chung: phiên đăng nhập, kiểm tra Origin (chống CSRF), kiểm tra vai trò và quyền sở hữu dữ liệu."""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import Assignment, DoctorProfile, SessionRow, User
from .security import as_utc, token_hash, utcnow

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(request: Request) -> str | None:
    o = request.headers.get("origin")
    if o:
        return o.rstrip("/")
    ref = request.headers.get("referer")
    if ref:
        p = urlparse(ref)
        return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None
    return None


def check_csrf(request: Request) -> None:
    """Yêu cầu thay đổi dữ liệu bằng cookie phải đến từ một origin được phép (SameSite=Lax là lớp bảo vệ thứ hai)."""
    if request.method in UNSAFE and request.cookies.get(config.COOKIE_NAME):
        origin = _origin_of(request)
        if origin not in config.ALLOWED_ORIGINS:
            raise HTTPException(403, "Yêu cầu bị từ chối (origin không hợp lệ).")


def current_session(request: Request, db: Session = Depends(get_db)) -> SessionRow:
    check_csrf(request)
    tok = request.cookies.get(config.COOKIE_NAME)
    if not tok:
        raise HTTPException(401, "Chưa đăng nhập.")
    s = db.get(SessionRow, token_hash(tok))
    if not s or s.revoked_at is not None or as_utc(s.expires_at) <= utcnow():
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
    return s


def current_user(session: SessionRow = Depends(current_session), db: Session = Depends(get_db)) -> User:
    u = db.get(User, session.user_id)
    if not u or u.status != "active":
        raise HTTPException(401, "Tài khoản không khả dụng.")
    return u


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Bạn không có quyền thực hiện thao tác này.")
        return user
    return dep


def doctor_is_approved(db: Session, doctor_id: str) -> bool:
    p = db.get(DoctorProfile, doctor_id)
    return bool(p and p.approved)


def doctor_assigned(db: Session, doctor_id: str, patient_id: str) -> bool:
    return db.scalar(select(Assignment.id).where(
        Assignment.doctor_id == doctor_id, Assignment.patient_id == patient_id,
        Assignment.ended_at.is_(None))) is not None


def patient_access(db: Session, user: User, patient_id: str) -> None:
    """Quyền truy cập dữ liệu sức khỏe của một bệnh nhân.

    - bệnh nhân: chỉ của chính mình;
    - bác sĩ: chỉ bệnh nhân đang được phân công và bác sĩ phải được phê duyệt;
    - admin: không có quyền đọc hồ sơ sức khỏe.
    Trả 404 (không phải 403) cho bác sĩ/bệnh nhân khi ngoài phạm vi để không lộ sự tồn tại của hồ sơ."""
    if user.role == "patient" and user.id == patient_id:
        return
    if user.role == "doctor" and doctor_is_approved(db, user.id) and doctor_assigned(db, user.id, patient_id):
        return
    if user.role == "admin":
        raise HTTPException(403, "Quản trị viên không được truy cập hồ sơ sức khỏe.")
    raise HTTPException(404, "Không tìm thấy hồ sơ.")


def get_patient_user(db: Session, patient_id: str) -> User:
    u = db.get(User, patient_id)
    if not u or u.role != "patient":
        raise HTTPException(404, "Không tìm thấy hồ sơ.")
    return u
