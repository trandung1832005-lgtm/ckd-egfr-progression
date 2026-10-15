from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import audit, config
from ..db import get_db
from ..deps import current_session, current_user
from ..models import DoctorProfile, PasswordToken, PatientProfile, SessionRow, User
from ..schemas import (ChangePasswordIn, ForgotIn, LoginIn, RegisterIn, ResetIn, UserOut)
from ..security import (as_utc, expires_in, hash_password, limiter, new_token, password_problem, send_email,
                        token_hash, utcnow, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
BAD_LOGIN = "Email hoặc mật khẩu không đúng."


def _start_session(db: Session, request: Request, response: Response, user: User) -> None:
    tok = new_token()
    db.add(SessionRow(id=token_hash(tok), user_id=user.id, expires_at=expires_in(hours=config.SESSION_TTL_HOURS),
                      ip=audit.client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:200]))
    db.commit()
    response.set_cookie(config.COOKIE_NAME, tok, max_age=config.SESSION_TTL_HOURS * 3600, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="lax", path="/")


def _revoke_user_sessions(db: Session, user_id: str, except_id: str | None = None) -> None:
    q = update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
    if except_id:
        q = q.where(SessionRow.id != except_id)
    db.execute(q.values(revoked_at=utcnow()))
    db.commit()


def _me(db: Session, user: User) -> dict:
    out = UserOut.model_validate(user).model_dump(mode="json")
    if user.role == "patient":
        p = db.get(PatientProfile, user.id)
        out["profile"] = {"birth_year": p.birth_year, "gender_code": p.gender_code} if p else {}
    elif user.role == "doctor":
        p = db.get(DoctorProfile, user.id)
        out["profile"] = {"specialty": p.specialty, "approved": p.approved} if p else {"approved": False}
    return out


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Chỉ tạo tài khoản BỆNH NHÂN. Bác sĩ/admin do quản trị viên tạo."""
    ip = audit.client_ip(request) or "?"
    if not limiter.hit(f"reg:{ip}", 10, 3600):
        raise HTTPException(429, "Bạn đã đăng ký quá nhiều lần. Vui lòng thử lại sau.")
    if not body.consent:
        raise HTTPException(422, "Cần đồng ý cho hệ thống xử lý dữ liệu sức khỏe của bạn để đăng ký.")
    email = body.email.lower()
    problem = password_problem(body.password, email)
    if problem:
        raise HTTPException(422, problem)
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email này đã được đăng ký.")
    user = User(email=email, password_hash=hash_password(body.password), role="patient", full_name=body.full_name)
    db.add(user)
    db.flush()
    db.add(PatientProfile(user_id=user.id, birth_year=body.birth_year, gender_code=body.gender_code,
                          consent_at=utcnow()))
    db.commit()
    audit.log(db, request, "auth.register", user, target_type="user", target_id=user.id)
    _start_session(db, request, response, user)
    return _me(db, user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = audit.client_ip(request) or "?"
    if not limiter.hit(f"login:{ip}", 30, 60):
        raise HTTPException(429, "Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.")
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user and user.locked_until and as_utc(user.locked_until) > utcnow():
        mins = int((as_utc(user.locked_until) - utcnow()).total_seconds() // 60) + 1
        raise HTTPException(429, f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau khoảng {mins} phút.")
    ok = verify_password(body.password, user.password_hash if user else None)
    if not user or not ok:
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= config.LOGIN_MAX_FAILS:
                user.locked_until = utcnow() + timedelta(minutes=config.LOGIN_LOCK_MINUTES)
                user.failed_attempts = 0
                audit.log(db, request, "auth.lockout", user, target_type="user", target_id=user.id, commit=False)
            db.commit()
        audit.log(db, request, "auth.login_failed", actor_id=user.id if user else None,
                  detail={"known_account": bool(user)})
        raise HTTPException(401, BAD_LOGIN)
    if user.status != "active":
        audit.log(db, request, "auth.login_blocked", user, target_type="user", target_id=user.id)
        raise HTTPException(403, "Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.")
    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, utcnow()
    db.commit()
    audit.log(db, request, "auth.login", user, target_type="user", target_id=user.id)
    _start_session(db, request, response, user)
    return _me(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: SessionRow = Depends(current_session),
           db: Session = Depends(get_db)):
    session.revoked_at = utcnow()
    db.commit()
    audit.log(db, request, "auth.logout", actor_id=session.user_id)
    response.delete_cookie(config.COOKIE_NAME, path="/")


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(db, user)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(current_user),
                    session: SessionRow = Depends(current_session), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Mật khẩu hiện tại không đúng.")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    _revoke_user_sessions(db, user.id, except_id=session.id)
    audit.log(db, request, "auth.password_changed", user, target_type="user", target_id=user.id)


@router.post("/forgot-password", status_code=202)
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Luôn trả cùng một phản hồi (không cho biết email có tồn tại hay không)."""
    email = body.email.lower()
    ip = audit.client_ip(request) or "?"
    generic = {"message": "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi."}
    if not limiter.hit(f"forgot:{ip}:{email}", 5, 3600):
        return generic
    user = db.scalar(select(User).where(User.email == email, User.status == "active"))
    if not user:
        return generic
    db.execute(update(PasswordToken).where(PasswordToken.user_id == user.id, PasswordToken.used_at.is_(None))
               .values(used_at=utcnow()))                       # vô hiệu các token cũ
    tok = new_token()
    db.add(PasswordToken(user_id=user.id, token_hash=token_hash(tok), purpose="reset",
                         expires_at=expires_in(minutes=config.RESET_TOKEN_TTL_MINUTES)))
    db.commit()
    link = f"{config.FRONTEND_URL}/reset-password?token={tok}"
    sent = send_email(user.email, "Đặt lại mật khẩu",
                      f"Xin chào {user.full_name},\n\nNhấn vào liên kết sau để đặt mật khẩu mới "
                      f"(hết hạn sau {config.RESET_TOKEN_TTL_MINUTES} phút, chỉ dùng một lần):\n{link}\n\n"
                      "Nếu bạn không yêu cầu, hãy bỏ qua email này.")
    audit.log(db, request, "auth.forgot_password", user, target_type="user", target_id=user.id,
              detail={"email_sent": sent})
    return generic


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    row = db.scalar(select(PasswordToken).where(PasswordToken.token_hash == token_hash(body.token)))
    if not row or row.used_at is not None or as_utc(row.expires_at) <= utcnow():
        raise HTTPException(400, "Liên kết không hợp lệ hoặc đã hết hạn.")
    user = db.get(User, row.user_id)
    if not user or user.status != "active":
        raise HTTPException(400, "Liên kết không hợp lệ hoặc đã hết hạn.")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password, user.failed_attempts, user.locked_until = False, 0, None
    row.used_at = utcnow()
    db.commit()
    _revoke_user_sessions(db, user.id)
    audit.log(db, request, "auth.password_reset", user, target_type="user", target_id=user.id,
              detail={"purpose": row.purpose})
