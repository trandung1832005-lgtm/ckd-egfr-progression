from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import doctor_is_approved, require_roles
from ..models import Assignment, EgfrRecord, Prediction, User

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/patients")
def my_patients(q: str | None = Query(None, max_length=80), user: User = Depends(require_roles("doctor")),
                db: Session = Depends(get_db)):
    """Chỉ trả bệnh nhân đang được phân công cho bác sĩ này."""
    if not doctor_is_approved(db, user.id):
        raise HTTPException(403, "Tài khoản bác sĩ chưa được phê duyệt.")
    stmt = (select(User).join(Assignment, Assignment.patient_id == User.id)
            .where(Assignment.doctor_id == user.id, Assignment.ended_at.is_(None), User.status == "active"))
    if q and q.strip():
        pat = _like(q.strip())
        stmt = stmt.where(or_(User.full_name.ilike(pat, escape="\\"), User.email.ilike(pat, escape="\\")))
    out = []
    for p in db.scalars(stmt.order_by(User.full_name).limit(200)):
        rec = db.scalar(select(EgfrRecord).where(EgfrRecord.patient_id == p.id, EgfrRecord.voided_at.is_(None))
                        .order_by(EgfrRecord.recorded_on.desc(), EgfrRecord.created_at.desc()))
        pred = db.scalar(select(Prediction).where(Prediction.patient_id == p.id).order_by(Prediction.created_at.desc()))
        r = json.loads(pred.result_json) if pred else None
        out.append({"id": p.id, "full_name": p.full_name, "email": p.email,
                    "latest_egfr": {"egfr": rec.egfr, "recorded_on": rec.recorded_on.isoformat()} if rec else None,
                    "latest_prediction": {"id": pred.id, "created_at": pred.created_at.isoformat(),
                                          "final_stage": r["final_stage"], "trend": r["gmm"]["name"]} if pred else None})
    return {"patients": out}
