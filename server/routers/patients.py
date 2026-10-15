from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, model_service as M
from ..db import get_db
from ..deps import current_user, doctor_is_approved, get_patient_user, patient_access, require_roles
from ..models import (Assignment, ClinicalNote, DoctorProfile, EgfrRecord, Prediction, PredictionInput,
                      PatientProfile, User, now)
from ..schemas import EgfrIn, NoteIn, PredictIn, ProfileIn
from ..security import limiter

router = APIRouter(prefix="/api", tags=["patients"])
SUGGEST_WINDOW_DAYS = 60


def _rec(r: EgfrRecord) -> dict:
    return {"id": r.id, "recorded_on": r.recorded_on.isoformat(), "egfr": r.egfr, "note": r.note, "source": r.source,
            "created_at": r.created_at.isoformat(), "replaces_id": r.replaces_id,
            "voided": r.voided_at is not None}


def _pred(p: Prediction, with_input: bool = False, db: Session | None = None) -> dict:
    out = {"id": p.id, "patient_id": p.patient_id, "created_at": p.created_at.isoformat(),
           "model_version": p.model_version, "created_by": p.created_by,
           "result": M.enrich(json.loads(p.result_json))}
    if with_input:
        i = p.input
        out["input"] = {"id": i.id, "egfr": {"0M": i.egfr_0m, "6M": i.egfr_6m, "12M": i.egfr_12m},
                        "clinical": json.loads(i.clinical_json), "created_at": i.created_at.isoformat(),
                        "replaces_id": i.replaces_id}
        if db is not None:
            u = db.get(User, p.created_by)
            out["created_by_name"] = u.full_name if u else None
            out["created_by_role"] = u.role if u else None
    return out


def _note(n: ClinicalNote, doctor_name: str | None) -> dict:
    return {"id": n.id, "doctor_id": n.doctor_id, "doctor_name": doctor_name, "body": n.body, "plan": n.plan,
            "follow_up_on": n.follow_up_on.isoformat() if n.follow_up_on else None,
            "prediction_id": n.prediction_id, "created_at": n.created_at.isoformat()}


def _active_records(db: Session, pid: str) -> list[EgfrRecord]:
    return list(db.scalars(select(EgfrRecord).where(EgfrRecord.patient_id == pid, EgfrRecord.voided_at.is_(None))
                           .order_by(EgfrRecord.recorded_on, EgfrRecord.created_at)))


def _who_source(user: User) -> str:
    return "patient" if user.role == "patient" else "doctor"


# ---------------- hồ sơ cá nhân ----------------
@router.put("/me/profile")
def update_my_profile(body: ProfileIn, request: Request, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    if body.full_name:
        user.full_name = body.full_name.strip()
    if user.role == "patient":
        p = db.get(PatientProfile, user.id)
        if p is None:
            p = PatientProfile(user_id=user.id)
            db.add(p)
        if body.birth_year is not None:
            p.birth_year = body.birth_year
        if body.gender_code is not None:
            p.gender_code = body.gender_code
    db.commit()
    audit.log(db, request, "profile.update", user, target_type="user", target_id=user.id)
    return {"ok": True}


# ---------------- chi tiết bệnh nhân ----------------
@router.get("/patients/{pid}")
def patient_detail(pid: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    pu = get_patient_user(db, pid)
    prof = db.get(PatientProfile, pid)
    recs = _active_records(db, pid)
    last_pred = db.scalar(select(Prediction).where(Prediction.patient_id == pid).order_by(Prediction.created_at.desc()))
    if user.role == "doctor":
        audit.log(db, request, "patient.view", user, target_type="patient", target_id=pid)
    return {
        "id": pu.id, "full_name": pu.full_name, "email": pu.email if user.role == "doctor" else None,
        "profile": {"birth_year": prof.birth_year if prof else None, "gender_code": prof.gender_code if prof else None},
        "egfr_count": len(recs), "latest_egfr": _rec(recs[-1]) if recs else None,
        "latest_prediction": _pred(last_pred) if last_pred else None,
    }


# ---------------- eGFR thực tế ----------------
@router.get("/patients/{pid}/egfr")
def list_egfr(pid: str, include_voided: bool = False, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    if include_voided:
        rows = list(db.scalars(select(EgfrRecord).where(EgfrRecord.patient_id == pid)
                               .order_by(EgfrRecord.recorded_on, EgfrRecord.created_at)))
    else:
        rows = _active_records(db, pid)
    return {"records": [_rec(r) for r in rows]}


@router.post("/patients/{pid}/egfr", status_code=201)
def add_egfr(pid: str, body: EgfrIn, request: Request, user: User = Depends(require_roles("patient", "doctor")),
             db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    r = EgfrRecord(patient_id=pid, recorded_on=body.recorded_on, egfr=body.egfr, note=body.note,
                   source=_who_source(user), created_by=user.id)
    db.add(r)
    db.commit()
    audit.log(db, request, "egfr.create", user, target_type="egfr_record", target_id=r.id, detail={"patient_id": pid})
    return _rec(r)


@router.post("/patients/{pid}/egfr/{rid}/replace", status_code=201)
def replace_egfr(pid: str, rid: str, body: EgfrIn, request: Request,
                 user: User = Depends(require_roles("patient", "doctor")), db: Session = Depends(get_db)):
    """Chỉnh sửa = tạo bản ghi mới thay thế, bản cũ bị vô hiệu nhưng vẫn được giữ trong lịch sử."""
    patient_access(db, user, pid)
    old = db.get(EgfrRecord, rid)
    if not old or old.patient_id != pid or old.voided_at is not None:
        raise HTTPException(404, "Không tìm thấy bản ghi.")
    new = EgfrRecord(patient_id=pid, recorded_on=body.recorded_on, egfr=body.egfr, note=body.note,
                     source=_who_source(user), created_by=user.id, replaces_id=old.id)
    db.add(new)
    old.voided_at, old.voided_by = now(), user.id
    db.commit()
    audit.log(db, request, "egfr.replace", user, target_type="egfr_record", target_id=new.id,
              detail={"patient_id": pid, "replaced": old.id})
    return _rec(new)


# ---------------- gợi ý đầu vào dự đoán ----------------
@router.get("/patients/{pid}/inputs/suggest")
def suggest_inputs(pid: str, baseline: date | None = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Điền sẵn eGFR 0/6/12M từ các bản ghi thực tế (người dùng vẫn chỉnh được trước khi gửi)."""
    patient_access(db, user, pid)
    recs = _active_records(db, pid)
    last_in = db.scalar(select(PredictionInput).where(PredictionInput.patient_id == pid)
                        .order_by(PredictionInput.created_at.desc()))
    out = {"egfr": {"0M": None, "6M": None, "12M": None}, "dates": {},
           "clinical": json.loads(last_in.clinical_json) if last_in else {}}
    if not recs:
        return out
    base = next((r for r in recs if baseline is None or r.recorded_on == baseline), None) or recs[0]
    out["egfr"]["0M"], out["dates"]["0M"] = base.egfr, base.recorded_on.isoformat()
    for key, days in (("6M", 182), ("12M", 365)):
        target = base.recorded_on + timedelta(days=days)
        cands = [r for r in recs if r.id != base.id and r.recorded_on > base.recorded_on
                 and abs((r.recorded_on - target).days) <= SUGGEST_WINDOW_DAYS]
        if cands:
            best = min(cands, key=lambda r: abs((r.recorded_on - target).days))
            out["egfr"][key], out["dates"][key] = best.egfr, best.recorded_on.isoformat()
    return out


# ---------------- dự đoán ----------------
@router.post("/patients/{pid}/predictions", status_code=201)
def create_prediction(pid: str, body: PredictIn, request: Request,
                      user: User = Depends(require_roles("patient", "doctor")), db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    if not limiter.hit(f"pred:{user.id}", 30, 60):
        raise HTTPException(429, "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.")
    if not M.engine.ready:
        raise HTTPException(503, "Mô hình chưa sẵn sàng. Vui lòng thử lại sau.")
    if body.replaces_input_id:
        prev = db.get(PredictionInput, body.replaces_input_id)
        if not prev or prev.patient_id != pid:
            raise HTTPException(404, "Không tìm thấy phiên bản đầu vào cần thay thế.")
    payload = {"egfr": {"0M": body.egfr.m0, "6M": body.egfr.m6, "12M": body.egfr.m12}, "clinical": body.clinical}
    try:
        result = M.engine.predict(payload)
    except M.InputError as e:
        raise HTTPException(422, str(e))
    except M.ModelNotReady as e:
        raise HTTPException(503, str(e))
    inp = PredictionInput(patient_id=pid, created_by=user.id, egfr_0m=body.egfr.m0, egfr_6m=body.egfr.m6,
                          egfr_12m=body.egfr.m12, clinical_json=json.dumps(body.clinical, ensure_ascii=False),
                          replaces_id=body.replaces_input_id)
    db.add(inp)
    db.flush()
    pred = Prediction(patient_id=pid, input_id=inp.id, created_by=user.id, model_version=M.model_version() or "?",
                      result_json=M.dumps(result))
    db.add(pred)
    db.commit()
    audit.log(db, request, "prediction.create", user, target_type="prediction", target_id=pred.id,
              detail={"patient_id": pid, "model_version": pred.model_version})
    return _pred(pred, with_input=True, db=db)


@router.get("/patients/{pid}/predictions")
def list_predictions(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    rows = db.scalars(select(Prediction).where(Prediction.patient_id == pid).order_by(Prediction.created_at.desc()))
    return {"predictions": [_pred(p, with_input=True, db=db) for p in rows]}


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: str, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    p = db.get(Prediction, prediction_id)
    if not p:
        raise HTTPException(404, "Không tìm thấy kết quả.")
    patient_access(db, user, p.patient_id)       # quyền xác định theo chủ sở hữu thật của kết quả, không theo ID client gửi
    if user.role == "doctor":
        audit.log(db, request, "prediction.view", user, target_type="prediction", target_id=p.id,
                  detail={"patient_id": p.patient_id})
    return _pred(p, with_input=True, db=db)


# ---------------- lịch sử tổng hợp ----------------
@router.get("/patients/{pid}/history")
def history(pid: str, limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    items = []
    for r in db.scalars(select(EgfrRecord).where(EgfrRecord.patient_id == pid)
                        .order_by(EgfrRecord.created_at.desc()).limit(limit)):
        items.append({"type": "egfr", "at": r.created_at.isoformat(), **_rec(r)})
    for p in db.scalars(select(Prediction).where(Prediction.patient_id == pid)
                        .order_by(Prediction.created_at.desc()).limit(limit)):
        items.append({"type": "prediction", "at": p.created_at.isoformat(), **_pred(p, with_input=True, db=db)})
    if user.role == "doctor":
        for n in db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == pid)
                            .order_by(ClinicalNote.created_at.desc()).limit(limit)):
            d = db.get(User, n.doctor_id)
            items.append({"type": "note", "at": n.created_at.isoformat(), **_note(n, d.full_name if d else None)})
    items.sort(key=lambda x: x["at"], reverse=True)
    return {"items": items[:limit]}


# ---------------- nhận xét chuyên môn (chỉ bác sĩ) ----------------
@router.get("/patients/{pid}/notes")
def list_notes(pid: str, user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    out = []
    for n in db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == pid).order_by(ClinicalNote.created_at.desc())):
        d = db.get(User, n.doctor_id)
        out.append(_note(n, d.full_name if d else None))
    return {"notes": out}


@router.post("/patients/{pid}/notes", status_code=201)
def add_note(pid: str, body: NoteIn, request: Request, user: User = Depends(require_roles("doctor")),
             db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    if body.prediction_id:
        p = db.get(Prediction, body.prediction_id)
        if not p or p.patient_id != pid:
            raise HTTPException(404, "Không tìm thấy kết quả dự đoán.")
    n = ClinicalNote(patient_id=pid, doctor_id=user.id, prediction_id=body.prediction_id, body=body.body.strip(),
                     plan=(body.plan or "").strip() or None, follow_up_on=body.follow_up_on)
    db.add(n)
    db.commit()
    audit.log(db, request, "note.create", user, target_type="note", target_id=n.id, detail={"patient_id": pid})
    return _note(n, user.full_name)


# ---------------- bác sĩ phụ trách (bệnh nhân xem) ----------------
@router.get("/patients/{pid}/doctors")
def my_doctors(pid: str, user: User = Depends(require_roles("patient")), db: Session = Depends(get_db)):
    patient_access(db, user, pid)
    out = []
    rows = db.scalars(select(Assignment).where(Assignment.patient_id == pid, Assignment.ended_at.is_(None)))
    for a in rows:
        d = db.get(User, a.doctor_id)
        dp = db.get(DoctorProfile, a.doctor_id)
        if d and d.status == "active" and doctor_is_approved(db, d.id):
            out.append({"id": d.id, "full_name": d.full_name, "specialty": dp.specialty if dp else None,
                        "assigned_at": a.created_at.isoformat()})
    return {"doctors": out}
