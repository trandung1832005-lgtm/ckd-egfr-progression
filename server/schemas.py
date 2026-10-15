from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    birth_year: int | None = Field(default=None, ge=1900, le=date.today().year)
    gender_code: Literal[1, 2] | None = None
    consent: bool

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Họ tên không được để trống.")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=128)


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_year: int | None = Field(default=None, ge=1900, le=date.today().year)
    gender_code: Literal[1, 2] | None = None


class EgfrIn(BaseModel):
    recorded_on: date
    egfr: float = Field(gt=0, le=200)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("recorded_on")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Ngày đo không được ở tương lai.")
        return v


class EgfrInputs(BaseModel):
    m0: float = Field(alias="0M", gt=0, le=200)
    m6: float | None = Field(default=None, alias="6M", gt=0, le=200)
    m12: float | None = Field(default=None, alias="12M", gt=0, le=200)
    model_config = {"populate_by_name": True}


class PredictIn(BaseModel):
    egfr: EgfrInputs
    clinical: dict[str, float] = Field(default_factory=dict)
    replaces_input_id: str | None = None   # tạo phiên bản mới của đầu vào cũ (giữ lịch sử)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    plan: str | None = Field(default=None, max_length=4000)
    follow_up_on: date | None = None
    prediction_id: str | None = None


class CreateUserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["patient", "doctor", "admin"]
    specialty: str | None = Field(default=None, max_length=120)
    license_no: str | None = Field(default=None, max_length=60)


class PatchUserIn(BaseModel):
    status: Literal["active", "locked"] | None = None
    approved: bool | None = None      # chỉ áp dụng cho bác sĩ


class AssignIn(BaseModel):
    doctor_id: str
    patient_id: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    status: str
    must_change_password: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    model_config = {"from_attributes": True}
