"""Kiểm thử xác thực, phân quyền (RBAC + quyền sở hữu), dữ liệu và tích hợp mô hình của backend đa người dùng.

Chạy:  pytest -q tests/test_server.py      (cần artifacts/ đã huấn luyện cho các test dự đoán)
"""
import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from server import config, model_service as M, security
from server.db import SessionLocal
from server.main import app
from server.models import (Assignment, AuditLog, ClinicalNote, DoctorProfile, EgfrRecord, PasswordToken, Prediction,
                           PredictionInput, SessionRow, User, PatientProfile)
from server.security import hash_password, limiter

ORIGIN = {"Origin": "http://localhost:3000"}
PW = "Matkhau12345"
CLIN = {"gender": 1, "age": 65, "hypertension": 1, "prevalence of CVD": 0, "diabetes": 1, "use of RAASi": 1,
        "use of CCB": 0, "use of diuretics": 0, "etiology of CKD": 1, "SBP": 140, "BMI": 24.5, "Hb": 12.1, "Alb": 3.9,
        "Cr": 1.8, "UPCR": 0.9, "proteinuria": 1, "CKD_stage": 3}
PRED = {"egfr": {"0M": 35.2, "6M": 33.0}, "clinical": CLIN}
needs_model = pytest.mark.skipif(not M.engine.ready, reason="Chưa có artifact; chạy scripts/train_all.py")

TABLES = ["audit_logs", "clinical_notes", "predictions", "prediction_inputs", "egfr_records", "password_tokens",
          "sessions", "doctor_patient_assignments", "doctor_profiles", "patient_profiles", "users"]


@pytest.fixture(autouse=True)
def clean_db():
    limiter.reset()
    with SessionLocal() as db:
        for t in TABLES:
            db.execute(text(f"DELETE FROM {t}"))
        db.commit()
    yield


def client() -> TestClient:
    c = TestClient(app, base_url="http://localhost")
    c.headers.update(ORIGIN)
    return c


def mk_user(role, email, name=None, approved=True, status="active") -> str:
    with SessionLocal() as db:
        u = User(email=email, full_name=name or email.split("@")[0], role=role, status=status,
                 password_hash=hash_password(PW))
        db.add(u)
        db.flush()
        if role == "doctor":
            db.add(DoctorProfile(user_id=u.id, approved=approved))
        if role == "patient":
            db.add(PatientProfile(user_id=u.id))
        db.commit()
        return u.id


def login(email, pw=PW) -> TestClient:
    c = client()
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return c


def assign(doctor_id, patient_id):
    with SessionLocal() as db:
        db.add(Assignment(doctor_id=doctor_id, patient_id=patient_id, assigned_by=doctor_id))
        db.commit()


@pytest.fixture
def world():
    """2 bệnh nhân, 2 bác sĩ (A phụ trách pa), 1 admin."""
    w = {
        "pa": mk_user("patient", "pa@x.com"), "pb": mk_user("patient", "pb@x.com"),
        "da": mk_user("doctor", "da@x.com"), "db": mk_user("doctor", "db@x.com"),
        "ad": mk_user("admin", "ad@x.com"),
    }
    assign(w["da"], w["pa"])
    return w


# ============================ XÁC THỰC ============================
def test_register_patient_and_me():
    c = client()
    r = c.post("/api/auth/register", json={"email": "New@X.com", "password": PW, "full_name": "Nguyễn A", "consent": True})
    assert r.status_code == 201 and r.json()["role"] == "patient" and r.json()["email"] == "new@x.com"
    assert "password_hash" not in r.text and "argon2" not in r.text
    assert c.get("/api/auth/me").json()["role"] == "patient"
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie


def test_register_cannot_choose_role_and_needs_consent_and_strong_password():
    c = client()
    r = c.post("/api/auth/register", json={"email": "evil@x.com", "password": PW, "full_name": "E", "consent": True,
                                           "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "patient"          # trường role bị bỏ qua
    assert client().post("/api/auth/register", json={"email": "a@x.com", "password": PW, "full_name": "A",
                                                     "consent": False}).status_code == 422
    for bad in ["short1", "onlyletterslong", "1234567890123"]:
        assert client().post("/api/auth/register", json={"email": "b@x.com", "password": bad, "full_name": "B",
                                                         "consent": True}).status_code == 422
    assert client().post("/api/auth/register", json={"email": "evil@x.com", "password": PW, "full_name": "E",
                                                     "consent": True}).status_code == 409


def test_password_is_hashed_with_argon2():
    mk_user("patient", "h@x.com")
    with SessionLocal() as db:
        h = db.scalar(select(User.password_hash).where(User.email == "h@x.com"))
    assert h.startswith("$argon2") and PW not in h


def test_login_wrong_password_generic_and_lockout():
    mk_user("patient", "l@x.com")
    r1 = client().post("/api/auth/login", json={"email": "l@x.com", "password": "saimatkhau123"})
    r2 = client().post("/api/auth/login", json={"email": "ghost@x.com", "password": "saimatkhau123"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()      # không lộ email có tồn tại
    for _ in range(config.LOGIN_MAX_FAILS):
        client().post("/api/auth/login", json={"email": "l@x.com", "password": "saimatkhau123"})
    r = client().post("/api/auth/login", json={"email": "l@x.com", "password": PW})   # đúng mật khẩu vẫn bị khóa tạm
    assert r.status_code == 429
    with SessionLocal() as db:                       # hết thời gian khóa -> đăng nhập lại được
        u = db.scalar(select(User).where(User.email == "l@x.com"))
        u.locked_until = security.utcnow() - timedelta(minutes=1)
        db.commit()
    assert client().post("/api/auth/login", json={"email": "l@x.com", "password": PW}).status_code == 200


def test_unauthenticated_requests_rejected():
    c = client()
    for path in ["/api/auth/me", "/api/doctor/patients", "/api/admin/overview", "/api/models/status"]:
        assert c.get(path).status_code == 401, path
    assert c.post("/api/patients/x/predictions", json=PRED).status_code == 401


def test_logout_revokes_session_server_side():
    mk_user("patient", "o@x.com")
    c = login("o@x.com")
    token = c.cookies.get(config.COOKIE_NAME)
    assert c.post("/api/auth/logout").status_code == 204
    c2 = client()
    c2.cookies.set(config.COOKIE_NAME, token)                 # dùng lại cookie cũ sau khi đăng xuất
    assert c2.get("/api/auth/me").status_code == 401


def test_session_expiry():
    mk_user("patient", "e@x.com")
    c = login("e@x.com")
    with SessionLocal() as db:
        s = db.scalar(select(SessionRow))
        s.expires_at = security.utcnow() - timedelta(seconds=1)
        db.commit()
    assert c.get("/api/auth/me").status_code == 401


def test_csrf_origin_check_blocks_foreign_origin():
    mk_user("patient", "c@x.com")
    c = login("c@x.com")
    r = c.post("/api/auth/change-password", json={"current_password": PW, "new_password": "Khac1234567"},
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = c.post("/api/auth/change-password", json={"current_password": PW, "new_password": "Khac1234567"},
               headers={"Origin": "", "Referer": "https://evil.example/page"})
    assert r.status_code == 403


def test_change_password_revokes_other_sessions():
    mk_user("patient", "cp@x.com")
    c1, c2 = login("cp@x.com"), login("cp@x.com")
    assert c1.post("/api/auth/change-password", json={"current_password": PW, "new_password": "Moi12345678"}).status_code == 204
    assert c1.get("/api/auth/me").status_code == 200           # phiên hiện tại giữ lại
    assert c2.get("/api/auth/me").status_code == 401           # phiên khác bị thu hồi
    assert client().post("/api/auth/login", json={"email": "cp@x.com", "password": PW}).status_code == 401
    assert client().post("/api/auth/login", json={"email": "cp@x.com", "password": "Moi12345678"}).status_code == 200
    bad = c1.post("/api/auth/change-password", json={"current_password": "sai", "new_password": "Moi12345679"})
    assert bad.status_code == 400


def test_forgot_and_reset_password_flow(monkeypatch):
    sent = []
    monkeypatch.setattr("server.routers.auth.send_email", lambda to, subj, body: sent.append((to, body)) or True)
    mk_user("patient", "f@x.com")
    old = login("f@x.com")
    r1 = client().post("/api/auth/forgot-password", json={"email": "f@x.com"})
    r2 = client().post("/api/auth/forgot-password", json={"email": "nobody@x.com"})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()         # không lộ tồn tại
    assert len(sent) == 1 and sent[0][0] == "f@x.com"
    token = sent[0][1].split("token=")[1].split()[0]
    with SessionLocal() as db:                         # token chỉ lưu hash
        assert db.scalar(select(PasswordToken.token_hash)) != token
    assert client().post("/api/auth/reset-password", json={"token": token, "new_password": "yeu"}).status_code == 422
    assert client().post("/api/auth/reset-password", json={"token": token, "new_password": "Datlai123456"}).status_code == 204
    assert client().post("/api/auth/reset-password", json={"token": token, "new_password": "Datlai1234567"}).status_code == 400  # một lần
    assert old.get("/api/auth/me").status_code == 401                                   # phiên cũ bị thu hồi
    assert client().post("/api/auth/login", json={"email": "f@x.com", "password": "Datlai123456"}).status_code == 200


def test_reset_token_expiry():
    uid = mk_user("patient", "x@x.com")
    with SessionLocal() as db:
        db.add(PasswordToken(user_id=uid, token_hash=security.token_hash("tok-expired-123456"), purpose="reset",
                             expires_at=security.utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client().post("/api/auth/reset-password", json={"token": "tok-expired-123456",
                                                           "new_password": "Datlai123456"}).status_code == 400


# ============================ ADMIN / TÀI KHOẢN ============================
def test_admin_creates_doctor_with_invite_and_no_default_password(world):
    a = login("ad@x.com")
    r = a.post("/api/admin/users", json={"email": "newdoc@x.com", "full_name": "BS Mới", "role": "doctor",
                                         "specialty": "Thận"})
    assert r.status_code == 201 and r.json()["invite_link"]                    # SMTP chưa cấu hình -> admin nhận link
    assert client().post("/api/auth/login", json={"email": "newdoc@x.com", "password": "anything12345"}).status_code == 401
    token = r.json()["invite_link"].split("token=")[1]
    assert client().post("/api/auth/reset-password", json={"token": token, "new_password": "BacSi12345678"}).status_code == 204
    d = login("newdoc@x.com", "BacSi12345678")
    assert d.get("/api/auth/me").json()["role"] == "doctor"


def test_non_admin_cannot_use_admin_api_or_escalate(world):
    for who in ("pa@x.com", "da@x.com"):
        c = login(who)
        for method, path, body in [("get", "/api/admin/overview", None), ("get", "/api/admin/users", None),
                                   ("post", "/api/admin/users", {"email": "z@x.com", "full_name": "Z", "role": "admin"}),
                                   ("patch", f"/api/admin/users/{world['pa']}", {"status": "locked"}),
                                   ("post", "/api/admin/assignments", {"doctor_id": world["da"], "patient_id": world["pb"]}),
                                   ("get", "/api/admin/audit-logs", None), ("get", "/api/admin/system", None)]:
            r = getattr(c, method)(path, **({"json": body} if body else {}))
            assert r.status_code == 403, (who, path, r.status_code)
    with SessionLocal() as db:
        assert db.get(User, world["pa"]).role == "patient"


def test_admin_lock_unlock_revokes_sessions_and_blocks_login(world):
    p, a = login("pa@x.com"), login("ad@x.com")
    assert a.patch(f"/api/admin/users/{world['pa']}", json={"status": "locked"}).status_code == 200
    assert p.get("/api/auth/me").status_code == 401                            # phiên hiện có bị thu hồi ngay
    r = client().post("/api/auth/login", json={"email": "pa@x.com", "password": PW})
    assert r.status_code == 403
    assert a.patch(f"/api/admin/users/{world['pa']}", json={"status": "active"}).status_code == 200
    assert client().post("/api/auth/login", json={"email": "pa@x.com", "password": PW}).status_code == 200
    assert a.patch(f"/api/admin/users/{world['ad']}", json={"status": "locked"}).status_code == 400   # không tự khóa mình


def test_assignment_rules(world):
    a = login("ad@x.com")
    assert a.post("/api/admin/assignments", json={"doctor_id": world["da"], "patient_id": world["pa"]}).status_code == 409
    assert a.post("/api/admin/assignments", json={"doctor_id": world["pa"], "patient_id": world["pb"]}).status_code == 422
    assert a.post("/api/admin/assignments", json={"doctor_id": world["da"], "patient_id": world["da"]}).status_code == 422
    with SessionLocal() as db:
        db.get(DoctorProfile, world["db"]).approved = False
        db.commit()
    assert a.post("/api/admin/assignments", json={"doctor_id": world["db"], "patient_id": world["pb"]}).status_code == 422
    assert a.patch(f"/api/admin/users/{world['db']}", json={"approved": True}).status_code == 200
    r = a.post("/api/admin/assignments", json={"doctor_id": world["db"], "patient_id": world["pb"]})
    assert r.status_code == 201
    assert a.delete(f"/api/admin/assignments/{r.json()['id']}").status_code == 204
    assert a.delete(f"/api/admin/assignments/{r.json()['id']}").status_code == 404


def test_db_unique_active_assignment_constraint(world):
    with SessionLocal() as db:
        db.add(Assignment(doctor_id=world["da"], patient_id=world["pa"], assigned_by=world["ad"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_foreign_keys_enforced(world):
    with SessionLocal() as db:
        db.add(EgfrRecord(patient_id="khong-ton-tai", recorded_on=date.today(), egfr=40, source="patient",
                          created_by=world["pa"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_admin_overview_counts_are_real(world):
    a = login("ad@x.com")
    o = a.get("/api/admin/overview").json()
    assert o["users_by_role"] == {"patient": 2, "doctor": 2, "admin": 1}
    assert o["active_assignments"] == 1 and o["patients_without_doctor"] == 1
    assert o["predictions_total"] == 0 and o["egfr_records_total"] == 0


# ============================ PHÂN QUYỀN DỮ LIỆU SỨC KHỎE ============================
def _add_record(c, pid, egfr=40.0, d=None):
    r = c.post(f"/api/patients/{pid}/egfr", json={"recorded_on": (d or date.today()).isoformat(), "egfr": egfr})
    assert r.status_code == 201, r.text
    return r.json()


def test_patient_cannot_access_other_patient(world):
    pa, pb = login("pa@x.com"), login("pb@x.com")
    rec = _add_record(pa, world["pa"])
    for method, path, body in [("get", f"/api/patients/{world['pa']}", None), ("get", f"/api/patients/{world['pa']}/egfr", None),
                               ("get", f"/api/patients/{world['pa']}/history", None),
                               ("get", f"/api/patients/{world['pa']}/predictions", None),
                               ("get", f"/api/patients/{world['pa']}/inputs/suggest", None),
                               ("post", f"/api/patients/{world['pa']}/egfr", {"recorded_on": date.today().isoformat(), "egfr": 50}),
                               ("post", f"/api/patients/{world['pa']}/egfr/{rec['id']}/replace", {"recorded_on": date.today().isoformat(), "egfr": 50}),
                               ("post", f"/api/patients/{world['pa']}/predictions", PRED)]:
        r = getattr(pb, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 404, (path, r.status_code)       # 404: không lộ hồ sơ có tồn tại
    assert pb.get(f"/api/patients/{world['pb']}/egfr").json()["records"] == []
    assert len(pa.get(f"/api/patients/{world['pa']}/egfr").json()["records"]) == 1


def test_patient_cannot_use_doctor_endpoints(world):
    pa = login("pa@x.com")
    assert pa.get("/api/doctor/patients").status_code == 403
    assert pa.get(f"/api/patients/{world['pa']}/notes").status_code == 403
    assert pa.post(f"/api/patients/{world['pa']}/notes", json={"body": "x"}).status_code == 403


def test_doctor_scope_follows_assignment(world):
    da, db_ = login("da@x.com"), login("db@x.com")
    assert da.get(f"/api/patients/{world['pa']}").status_code == 200
    assert db_.get(f"/api/patients/{world['pa']}").status_code == 404          # bác sĩ khác không được xem
    assert da.get(f"/api/patients/{world['pb']}").status_code == 404           # bệnh nhân không được phân công
    assert [p["id"] for p in da.get("/api/doctor/patients").json()["patients"]] == [world["pa"]]
    assert db_.get("/api/doctor/patients").json()["patients"] == []
    a = login("ad@x.com")
    aid = a.get("/api/admin/assignments").json()["assignments"][0]["id"]
    assert a.delete(f"/api/admin/assignments/{aid}").status_code == 204        # thu hồi có hiệu lực ngay
    assert da.get(f"/api/patients/{world['pa']}").status_code == 404
    assert da.get("/api/doctor/patients").json()["patients"] == []


def test_unapproved_or_revoked_doctor_loses_access(world):
    da, a = login("da@x.com"), login("ad@x.com")
    assert a.patch(f"/api/admin/users/{world['da']}", json={"approved": False}).status_code == 200
    assert da.get(f"/api/patients/{world['pa']}").status_code == 404
    assert da.get("/api/doctor/patients").status_code == 403


def test_admin_cannot_read_health_data(world):
    pa, a = login("pa@x.com"), login("ad@x.com")
    _add_record(pa, world["pa"])
    for path in [f"/api/patients/{world['pa']}", f"/api/patients/{world['pa']}/egfr", f"/api/patients/{world['pa']}/history",
                 f"/api/patients/{world['pa']}/predictions"]:
        assert a.get(path).status_code == 403, path
    assert a.post(f"/api/patients/{world['pa']}/egfr", json={"recorded_on": date.today().isoformat(), "egfr": 40}).status_code == 403
    assert a.post(f"/api/patients/{world['pa']}/predictions", json=PRED).status_code == 403
    users = a.get("/api/admin/users?role=patient").json()["users"]
    assert users and all("egfr" not in json.dumps(u).lower() for u in users)    # danh sách tài khoản không chứa dữ liệu y tế


def test_doctor_can_add_records_for_assigned_patient_only(world):
    da = login("da@x.com")
    r = _add_record(da, world["pa"], 41.0)
    assert r["source"] == "doctor"
    assert da.post(f"/api/patients/{world['pb']}/egfr", json={"recorded_on": date.today().isoformat(), "egfr": 41}).status_code == 404


def test_egfr_validation():
    mk_user("patient", "v@x.com")
    c = login("v@x.com")
    pid = c.get("/api/auth/me").json()["id"]
    future = (date.today() + timedelta(days=2)).isoformat()
    for body in [{"recorded_on": future, "egfr": 40}, {"recorded_on": date.today().isoformat(), "egfr": -3},
                 {"recorded_on": date.today().isoformat(), "egfr": 999}, {"recorded_on": "not-a-date", "egfr": 40},
                 {"recorded_on": date.today().isoformat(), "egfr": "abc"}]:
        assert c.post(f"/api/patients/{pid}/egfr", json=body).status_code == 422, body


def test_egfr_replace_keeps_history(world):
    pa = login("pa@x.com")
    r = _add_record(pa, world["pa"], 40.0)
    n = pa.post(f"/api/patients/{world['pa']}/egfr/{r['id']}/replace", json={"recorded_on": date.today().isoformat(), "egfr": 42.5})
    assert n.status_code == 201 and n.json()["replaces_id"] == r["id"]
    active = pa.get(f"/api/patients/{world['pa']}/egfr").json()["records"]
    assert [x["egfr"] for x in active] == [42.5]
    allrec = pa.get(f"/api/patients/{world['pa']}/egfr?include_voided=true").json()["records"]
    assert len(allrec) == 2 and sum(x["voided"] for x in allrec) == 1
    assert pa.post(f"/api/patients/{world['pa']}/egfr/{r['id']}/replace", json={"recorded_on": date.today().isoformat(), "egfr": 1}).status_code == 404


def test_suggest_inputs_from_records(world):
    pa = login("pa@x.com")
    t0 = date.today() - timedelta(days=400)
    _add_record(pa, world["pa"], 40.0, t0)
    _add_record(pa, world["pa"], 38.0, t0 + timedelta(days=180))
    _add_record(pa, world["pa"], 35.0, t0 + timedelta(days=370))
    _add_record(pa, world["pa"], 30.0, t0 + timedelta(days=250))       # ngoài cửa sổ 6M/12M -> không được chọn
    s = pa.get(f"/api/patients/{world['pa']}/inputs/suggest").json()
    assert s["egfr"] == {"0M": 40.0, "6M": 38.0, "12M": 35.0}


# ============================ DỰ ĐOÁN (mô hình thật) ============================
@needs_model
def test_prediction_matches_engine_and_is_stored(world):
    pa = login("pa@x.com")
    r = pa.post(f"/api/patients/{world['pa']}/predictions", json=PRED)
    assert r.status_code == 201, r.text
    j = r.json()
    direct = M.engine.predict(copy.deepcopy(PRED))
    assert [round(f["egfr"], 6) for f in j["result"]["forecast"]] == [round(f["egfr"], 6) for f in direct["forecast"]]
    assert j["result"]["gmm"]["name"] == direct["gmm"]["name"] and j["model_version"].startswith("gru-seed")
    assert j["input"]["egfr"]["12M"] is None and j["input"]["clinical"]["age"] == 65
    got = pa.get(f"/api/predictions/{j['id']}").json()
    assert got["result"]["forecast"] == j["result"]["forecast"]
    assert j["result"]["guidance"]["stage"] == j["result"]["final_stage"]
    hist = pa.get(f"/api/patients/{world['pa']}/history").json()["items"]
    assert [i["type"] for i in hist] == ["prediction"]
    with SessionLocal() as db:
        assert db.scalar(select(Prediction.patient_id)) == world["pa"]           # gắn đúng bệnh nhân


@needs_model
def test_prediction_access_by_owner_not_by_client_supplied_id(world):
    pa, pb, da, db_ = login("pa@x.com"), login("pb@x.com"), login("da@x.com"), login("db@x.com")
    pid = pa.post(f"/api/patients/{world['pa']}/predictions", json=PRED).json()["id"]
    assert pb.get(f"/api/predictions/{pid}").status_code == 404
    assert db_.get(f"/api/predictions/{pid}").status_code == 404
    assert da.get(f"/api/predictions/{pid}").status_code == 200
    assert login("ad@x.com").get(f"/api/predictions/{pid}").status_code == 403


@needs_model
def test_doctor_runs_prediction_for_assigned_patient(world):
    da = login("da@x.com")
    r = da.post(f"/api/patients/{world['pa']}/predictions", json=PRED)
    assert r.status_code == 201 and r.json()["created_by_role"] == "doctor"
    assert da.post(f"/api/patients/{world['pb']}/predictions", json=PRED).status_code == 404


@needs_model
@pytest.mark.parametrize("mut", [
    lambda p: p["egfr"].pop("0M"),
    lambda p: p["egfr"].update({"0M": -5}),
    lambda p: p["egfr"].update({"0M": 999}),
    lambda p: p["egfr"].update({"0M": "abc"}),
    lambda p: p["clinical"].pop("age"),
    lambda p: p["clinical"].update({"diabetes": 7}),
    lambda p: p["clinical"].update({"etiology of CKD": 9}),
])
def test_prediction_rejects_bad_input_without_leaking(world, mut):
    pa = login("pa@x.com")
    p = copy.deepcopy(PRED)
    mut(p)
    r = pa.post(f"/api/patients/{world['pa']}/predictions", json=p)
    assert r.status_code == 422
    assert "Traceback" not in r.text and ".py" not in r.text
    with SessionLocal() as db:
        assert db.scalar(select(Prediction.id)) is None and db.scalar(select(PredictionInput.id)) is None


def test_prediction_503_when_model_not_ready(world, monkeypatch):
    monkeypatch.setattr(M.engine, "ready", False)
    r = login("pa@x.com").post(f"/api/patients/{world['pa']}/predictions", json=PRED)
    assert r.status_code == 503 and "chưa sẵn sàng" in r.json()["detail"]


@needs_model
def test_input_versioning_keeps_old_input(world):
    pa = login("pa@x.com")
    first = pa.post(f"/api/patients/{world['pa']}/predictions", json=PRED).json()
    fixed = copy.deepcopy(PRED)
    fixed["egfr"]["12M"] = 30.0
    fixed["replaces_input_id"] = first["input"]["id"]
    second = pa.post(f"/api/patients/{world['pa']}/predictions", json=fixed).json()
    assert second["input"]["replaces_id"] == first["input"]["id"] and second["id"] != first["id"]
    old = pa.get(f"/api/predictions/{first['id']}").json()
    assert old["input"]["egfr"]["12M"] is None                     # bản cũ không bị ghi đè
    pb = login("pb@x.com")
    bad = copy.deepcopy(PRED)
    bad["replaces_input_id"] = first["input"]["id"]
    assert pb.post(f"/api/patients/{world['pb']}/predictions", json=bad).status_code == 404   # không thay thế input của người khác


@needs_model
def test_models_status_visibility(world):
    assert login("pa@x.com").get("/api/models/status").json() == {"ready": True}
    s = login("ad@x.com").get("/api/models/status").json()
    assert s["ready"] and s["version"].startswith("gru-seed")


# ============================ NHẬN XÉT & BÁC SĨ PHỤ TRÁCH ============================
@needs_model
def test_clinical_notes_doctor_only_and_scoped(world):
    pa, pb, da, db_ = login("pa@x.com"), login("pb@x.com"), login("da@x.com"), login("db@x.com")
    pred = pa.post(f"/api/patients/{world['pa']}/predictions", json=PRED).json()["id"]
    n = da.post(f"/api/patients/{world['pa']}/notes", json={"body": "Tái khám sau 3 tháng", "plan": "Theo dõi eGFR",
                                                            "follow_up_on": "2030-01-01", "prediction_id": pred})
    assert n.status_code == 201
    assert da.get(f"/api/patients/{world['pa']}/notes").json()["notes"][0]["body"] == "Tái khám sau 3 tháng"
    assert db_.get(f"/api/patients/{world['pa']}/notes").status_code == 404
    assert pa.get(f"/api/patients/{world['pa']}/notes").status_code == 403
    # bệnh nhân không thấy nhận xét trong lịch sử của chính mình
    assert all(i["type"] != "note" for i in pa.get(f"/api/patients/{world['pa']}/history").json()["items"])
    assert any(i["type"] == "note" for i in da.get(f"/api/patients/{world['pa']}/history").json()["items"])
    other = login("pb@x.com").post(f"/api/patients/{world['pb']}/predictions", json=PRED).json()["id"]
    assert da.post(f"/api/patients/{world['pa']}/notes", json={"body": "x", "prediction_id": other}).status_code == 404


def test_patient_sees_assigned_doctors(world):
    docs = login("pa@x.com").get(f"/api/patients/{world['pa']}/doctors").json()["doctors"]
    assert [d["id"] for d in docs] == [world["da"]]
    assert login("pb@x.com").get(f"/api/patients/{world['pb']}/doctors").json()["doctors"] == []


def test_doctor_patient_search_is_escaped_and_scoped(world):
    da = login("da@x.com")
    assert len(da.get("/api/doctor/patients?q=pa").json()["patients"]) == 1
    assert da.get("/api/doctor/patients?q=pb").json()["patients"] == []
    assert da.get("/api/doctor/patients?q=%25").json()["patients"] == []          # '%' không phải ký tự đại diện
    assert da.get("/api/doctor/patients?q=" + "x" * 200).status_code == 422


# ============================ NHẬT KÝ KIỂM TOÁN ============================
@needs_model
def test_audit_log_records_sensitive_actions_without_secrets(world):
    client().post("/api/auth/login", json={"email": "pa@x.com", "password": "SaiMatKhau999"})
    pa, da, a = login("pa@x.com"), login("da@x.com"), login("ad@x.com")
    pa.post(f"/api/patients/{world['pa']}/predictions", json=PRED)
    da.get(f"/api/patients/{world['pa']}")
    a.patch(f"/api/admin/users/{world['pb']}", json={"status": "locked"})
    logs = a.get("/api/admin/audit-logs?limit=200").json()["logs"]
    actions = {l["action"] for l in logs}
    assert {"auth.login", "auth.login_failed", "prediction.create", "patient.view", "admin.user_lock"} <= actions
    dump = json.dumps(logs, ensure_ascii=False)
    assert "SaiMatKhau999" not in dump and PW not in dump and "35.2" not in dump and "Cr" not in dump
    only = a.get("/api/admin/audit-logs?action=patient.view").json()
    assert only["total"] == 1 and only["logs"][0]["actor_role"] == "doctor"


def test_health_is_public_and_minimal():
    r = client().get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_security_headers_and_no_cache():
    r = client().get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-frame-options"] == "DENY"


def test_cors_only_allows_configured_origin():
    r = client().options("/api/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
    ok = client().options("/api/auth/login", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_manage_create_admin_refuses_weak_password_and_duplicates():
    from server import manage
    with pytest.raises(SystemExit):
        manage.create_admin("boss@x.com", "Boss", "weak")
    manage.create_admin("boss@x.com", "Boss", "ManhLam123456")
    with pytest.raises(SystemExit):
        manage.create_admin("boss@x.com", "Boss", "ManhLam123456")
    c = login("boss@x.com", "ManhLam123456")
    assert c.get("/api/auth/me").json()["role"] == "admin"


# ============================ IP KHÁCH SAU PROXY ============================
def _req(xff, host="10.0.0.1"):
    from starlette.requests import Request
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (host, 1234), "query_string": b""})


def test_client_ip_ignores_spoofed_forwarded_for_by_default(monkeypatch):
    from server import audit
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    assert audit.client_ip(_req("6.6.6.6")) == "10.0.0.1"


def test_client_ip_trusts_only_configured_hops(monkeypatch):
    from server import audit
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 2)       # Vercel -> Render: "khách, vercel"
    assert audit.client_ip(_req("1.2.3.4, 76.76.21.1")) == "1.2.3.4"
    assert audit.client_ip(_req("6.6.6.6, 1.2.3.4, 76.76.21.1")) == "1.2.3.4"    # phần tử giả bên trái bị bỏ qua
    assert audit.client_ip(_req(None)) == "10.0.0.1"
