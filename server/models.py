"""Lược đồ cơ sở dữ liệu. ID dùng UUID để không đoán được; mọi truy cập dữ liệu đều đi qua kiểm tra quyền ở backend."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


ROLES = ("patient", "doctor", "admin")
STATUSES = ("active", "locked")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active")
    full_name: Mapped[str] = mapped_column(String(120))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    patient_profile: Mapped["PatientProfile | None"] = relationship(back_populates="user", uselist=False)
    doctor_profile: Mapped["DoctorProfile | None"] = relationship(back_populates="user", uselist=False,
                                                                  foreign_keys="DoctorProfile.user_id")


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender_code: Mapped[int | None] = mapped_column(Integer, nullable=True)   # mã 1/2 theo dữ liệu huấn luyện
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    user: Mapped[User] = relationship(back_populates="patient_profile")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    specialty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    user: Mapped[User] = relationship(back_populates="doctor_profile", foreign_keys=[user_id])


class Assignment(Base):
    """Phân công bác sĩ – bệnh nhân. Chỉ phân công đang hiệu lực (ended_at IS NULL) mới cấp quyền truy cập."""
    __tablename__ = "doctor_patient_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        Index("uq_active_assignment", "doctor_id", "patient_id", unique=True,
              sqlite_where=text("ended_at IS NULL"), postgresql_where=text("ended_at IS NULL")),
    )


class EgfrRecord(Base):
    """eGFR thực tế. Không sửa tại chỗ: chỉnh sửa tạo bản ghi mới (replaces_id) và vô hiệu bản cũ, giữ lịch sử."""
    __tablename__ = "egfr_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recorded_on: Mapped[date] = mapped_column(Date)
    egfr: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source: Mapped[str] = mapped_column(String(16))               # patient | doctor
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("egfr_records.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (Index("ix_egfr_patient_date", "patient_id", "recorded_on"),)


class PredictionInput(Base):
    """Phiên bản đầu vào bất biến đã dùng cho một lần dự đoán (eGFR 0/6/12M + biến lâm sàng)."""
    __tablename__ = "prediction_inputs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    egfr_0m: Mapped[float] = mapped_column(Float)
    egfr_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    egfr_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    clinical_json: Mapped[str] = mapped_column(Text)
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("prediction_inputs.id"), nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    input_id: Mapped[str] = mapped_column(ForeignKey("prediction_inputs.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    model_version: Mapped[str] = mapped_column(String(80))
    result_json: Mapped[str] = mapped_column(Text)
    input: Mapped[PredictionInput] = relationship()


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    prediction_id: Mapped[str | None] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)   # không FK: giữ log khi xóa user
    actor_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)                        # JSON, không chứa bí mật/dữ liệu y tế


class SessionRow(Base):
    """Phiên đăng nhập phía máy chủ (thu hồi được). Khóa chính là HMAC của token trong cookie, không lưu token thô."""
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PasswordToken(Base):
    """Token đặt lại mật khẩu / mời kích hoạt: một lần, hết hạn ngắn, chỉ lưu hash."""
    __tablename__ = "password_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))              # reset | invite
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
