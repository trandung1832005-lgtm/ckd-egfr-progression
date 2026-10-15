from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from .. import audit, config, model_service as M
from ..db import get_db
from ..deps import require_roles
from ..models import (Assignment, AuditLog, DoctorProfile, EgfrRecord, PasswordToken, PatientProfile, Prediction,
                      SessionRow, User, now)
from ..schemas import AssignIn, CreateUserIn, PatchUserIn, UserOut
from ..security import expires_in, hash_password, new_token, send_email, token_hash, utcnow
from .doctor import _like

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles("admin")


def _issue_token(db: Session, user: User, purpose: str) -> str:
    db.execute(update(PasswordToken).where(PasswordToken.user_id == user.id, PasswordToken.used_at.is_(None))
               .values(used_at=utcnow()))
    tok = new_token()
    ttl = expires_in(hours=config.INVITE_TOKEN_TTL_HOURS) if purpose == "invite" else expires_in(minutes=config.RESET_TOKEN_TTL_MINUTES)
    db.add(PasswordToken(user_id=user.id, token_hash=token_hash(tok), purpose=purpose, expires_at=ttl))
    db.commit()
    return f"{config.FRONTEND_URL}/reset-password?token={tok}"


def _user_row(db: Session, u: User) -> dict:
    out = UserOut.model_validate(u).model_dump(mode="json")
    if u.role == "doctor":
        dp = db.get(DoctorProfile, u.id)
        out["doctor"] = {"specialty": dp.specialty, "license_no": dp.license_no, "approved": dp.approved} if dp else None
    return out


@router.get("/overview")
def overview(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Chỉ là số đếm thật từ cơ sở dữ liệu; không chứa nội dung hồ sơ sức khỏe."""
    by_role = {r: db.scalar(select(func.count()).select_from(User).where(User.role == r)) for r in ("patient", "doctor", "admin")}
    return {
        "users_by_role": by_role,
        "locked_users": db.scalar(select(func.count()).select_from(User).where(User.status == "locked")),
        "doctors_pending_approval": db.scalar(select(func.count()).select_from(DoctorProfile).where(DoctorProfile.approved.is_(False))),
        "active_assignments": db.scalar(select(func.count()).select_from(Assignment).where(Assignment.ended_at.is_(None))),
        "patients_without_doctor": db.scalar(select(func.count()).select_from(User).where(
            User.role == "patient",
            ~select(Assignment.id).where(Assignment.patient_id == User.id, Assignment.ended_at.is_(None)).exists())),
        "predictions_total": db.scalar(select(func.count()).select_from(Prediction)),
        "egfr_records_total": db.scalar(select(func.count()).select_from(EgfrRecord)),
        "logins_last_24h": db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "auth.login", AuditLog.at >= utcnow() - timedelta(hours=24))),
        "failed_logins_last_24h": db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "auth.login_failed", AuditLog.at >= utcnow() - timedelta(hours=24))),
    }


@router.get("/users")
def list_users(role: str | None = Query(None, pattern="^(patient|doctor|admin)$"),
               status: str | None = Query(None, pattern="^(active|locked)$"), q: str | None = Query(None, max_length=80),
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               user: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if q and q.strip():
        pat = _like(q.strip())
        stmt = stmt.where(or_(User.full_name.ilike(pat, escape="\\"), User.email.ilike(pat, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    return {"total": total, "users": [_user_row(db, u) for u in rows]}


@router.post("/users", status_code=201)
def create_user(body: CreateUserIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Tạo tài khoản kèm liên kết kích hoạt dùng một lần (người dùng tự đặt mật khẩu). Không có mật khẩu mặc định."""
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email này đã được đăng ký.")
    u = User(email=email, full_name=body.full_name.strip(), role=body.role,
             password_hash=hash_password(secrets.token_urlsafe(32)))     # mật khẩu ngẫu nhiên không ai biết
    db.add(u)
    db.flush()
    if body.role == "doctor":
        db.add(DoctorProfile(user_id=u.id, specialty=body.specialty, license_no=body.license_no, approved=True,
                             approved_by=admin.id, approved_at=now()))
    elif body.role == "patient":
        db.add(PatientProfile(user_id=u.id))
    db.commit()
    link = _issue_token(db, u, "invite")
    sent = send_email(u.email, "Kích hoạt tài khoản",
                      f"Xin chào {u.full_name},\n\nTài khoản của bạn đã được tạo. Nhấn vào liên kết sau để đặt mật khẩu "
                      f"(hết hạn sau {config.INVITE_TOKEN_TTL_HOURS} giờ, chỉ dùng một lần):\n{link}\n")
    audit.log(db, request, "admin.user_create", admin, target_type="user", target_id=u.id,
              detail={"role": body.role, "email_sent": sent})
    out = {"user": _user_row(db, u), "email_sent": sent}
    if not sent:                               # chưa cấu hình SMTP: admin tự chuyển liên kết (chỉ hiển thị một lần)
        out["invite_link"] = link
    return out


@router.patch("/users/{uid}")
def patch_user(uid: str, body: PatchUserIn, request: Request, admin: User = Depends(admin_only),
               db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản.")
    if body.status is not None:
        if u.id == admin.id:
            raise HTTPException(400, "Bạn không thể khóa chính tài khoản của mình.")
        u.status = body.status
        if body.status == "locked":
            db.execute(update(SessionRow).where(SessionRow.user_id == u.id, SessionRow.revoked_at.is_(None))
                       .values(revoked_at=utcnow()))      # đăng xuất mọi phiên ngay
        else:
            u.failed_attempts, u.locked_until = 0, None
        audit.log(db, request, f"admin.user_{'lock' if body.status == 'locked' else 'unlock'}", admin,
                  target_type="user", target_id=u.id, commit=False)
    if body.approved is not None:
        if u.role != "doctor":
            raise HTTPException(400, "Chỉ áp dụng cho tài khoản bác sĩ.")
        dp = db.get(DoctorProfile, u.id) or DoctorProfile(user_id=u.id)
        dp.approved, dp.approved_by, dp.approved_at = body.approved, admin.id, now()
        db.add(dp)
        audit.log(db, request, f"admin.doctor_{'approve' if body.approved else 'revoke'}", admin,
                  target_type="user", target_id=u.id, commit=False)
    db.commit()
    return _user_row(db, u)


@router.post("/users/{uid}/reset-link")
def reset_link(uid: str, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản.")
    link = _issue_token(db, u, "reset")
    sent = send_email(u.email, "Đặt lại mật khẩu",
                      f"Quản trị viên đã tạo liên kết đặt lại mật khẩu cho bạn (hết hạn sau "
                      f"{config.RESET_TOKEN_TTL_MINUTES} phút, chỉ dùng một lần):\n{link}\n")
    audit.log(db, request, "admin.reset_link", admin, target_type="user", target_id=u.id, detail={"email_sent": sent})
    out = {"email_sent": sent}
    if not sent:
        out["reset_link"] = link
    return out


@router.get("/assignments")
def list_assignments(active: bool | None = True, doctor_id: str | None = None, patient_id: str | None = None,
                     admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(Assignment)
    if active is True:
        stmt = stmt.where(Assignment.ended_at.is_(None))
    elif active is False:
        stmt = stmt.where(Assignment.ended_at.is_not(None))
    if doctor_id:
        stmt = stmt.where(Assignment.doctor_id == doctor_id)
    if patient_id:
        stmt = stmt.where(Assignment.patient_id == patient_id)
    out = []
    for a in db.scalars(stmt.order_by(Assignment.created_at.desc()).limit(500)):
        d, p = db.get(User, a.doctor_id), db.get(User, a.patient_id)
        out.append({"id": a.id, "doctor": {"id": a.doctor_id, "full_name": d.full_name if d else None},
                    "patient": {"id": a.patient_id, "full_name": p.full_name if p else None},
                    "created_at": a.created_at.isoformat(), "ended_at": a.ended_at.isoformat() if a.ended_at else None})
    return {"assignments": out}


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d, p = db.get(User, body.doctor_id), db.get(User, body.patient_id)
    if not d or d.role != "doctor" or d.status != "active":
        raise HTTPException(422, "Bác sĩ không hợp lệ.")
    dp = db.get(DoctorProfile, d.id)
    if not dp or not dp.approved:
        raise HTTPException(422, "Bác sĩ chưa được phê duyệt.")
    if not p or p.role != "patient" or p.status != "active":
        raise HTTPException(422, "Bệnh nhân không hợp lệ.")
    if db.scalar(select(Assignment.id).where(Assignment.doctor_id == d.id, Assignment.patient_id == p.id,
                                             Assignment.ended_at.is_(None))):
        raise HTTPException(409, "Bác sĩ đã được phân công cho bệnh nhân này.")
    a = Assignment(doctor_id=d.id, patient_id=p.id, assigned_by=admin.id)
    db.add(a)
    db.commit()
    audit.log(db, request, "admin.assign", admin, target_type="assignment", target_id=a.id,
              detail={"doctor_id": d.id, "patient_id": p.id})
    return {"id": a.id}


@router.delete("/assignments/{aid}", status_code=204)
def end_assignment(aid: str, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    a = db.get(Assignment, aid)
    if not a or a.ended_at is not None:
        raise HTTPException(404, "Không tìm thấy phân công đang hiệu lực.")
    a.ended_at, a.ended_by = now(), admin.id
    db.commit()
    audit.log(db, request, "admin.unassign", admin, target_type="assignment", target_id=a.id,
              detail={"doctor_id": a.doctor_id, "patient_id": a.patient_id})


@router.get("/audit-logs")
def audit_logs(action: str | None = Query(None, max_length=60), actor_id: str | None = Query(None, max_length=36),
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    names = {}
    out = []
    for r in rows:
        if r.actor_id and r.actor_id not in names:
            u = db.get(User, r.actor_id)
            names[r.actor_id] = u.full_name if u else None
        out.append({"id": r.id, "at": r.at.isoformat(), "actor_id": r.actor_id, "actor_name": names.get(r.actor_id),
                    "actor_role": r.actor_role, "action": r.action, "target_type": r.target_type,
                    "target_id": r.target_id, "ip": r.ip, "detail": r.detail})
    return {"total": total, "logs": out}


@router.get("/system")
def system(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"api": "ok", "database": {"ok": db_ok, "kind": config.DATABASE_URL.split(":", 1)[0].split("+")[0]},
            "model": M.status(), "smtp_configured": config.SMTP_CONFIGURED, "env": config.APP_ENV,
            "allowed_origins": config.ALLOWED_ORIGINS, "cookie_secure": config.COOKIE_SECURE,
            "session_ttl_hours": config.SESSION_TTL_HOURS}
