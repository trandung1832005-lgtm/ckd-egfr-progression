"""Kiểm thử API với mô hình đã huấn luyện thật.  pytest -q tests"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app, engine  # noqa: E402
from ckd_core import config as C  # noqa: E402

pytestmark = pytest.mark.skipif(not engine.ready, reason="Chưa có artifact; chạy scripts/train_all.py")
client = TestClient(app)

GOOD = {
    "egfr": {"0M": 35.2, "6M": 33.0, "12M": None},
    "clinical": {"gender": 1, "age": 65, "hypertension": 1, "prevalence of CVD": 0, "diabetes": 1,
                 "use of RAASi": 1, "use of CCB": 0, "use of diuretics": 0, "etiology of CKD": 1,
                 "SBP": 140, "BMI": 24.5, "Hb": 12.1, "Alb": 3.9, "Cr": 1.8, "UPCR": 0.9,
                 "proteinuria": 1, "CKD_stage": 3},
}


def test_health_meta_results():
    assert client.get("/api/health").json()["model_ready"] is True
    assert client.get("/api/meta").json()["future_months"] == [18, 24, 30, 36]
    r = client.get("/api/results").json()
    assert r["regression"] and r["gmm_profile"] and r["gmm_trajectories"]


def test_predict_ok():
    r = client.post("/api/predict", json=GOOD)
    assert r.status_code == 200
    j = r.json()
    assert [f["month"] for f in j["forecast"]] == [18, 24, 30, 36]
    assert all(0 <= f["egfr"] < 200 for f in j["forecast"])
    assert abs(sum(j["gmm"]["probabilities"]) - 1) < 1e-6


def test_pipeline_consistency_with_batch_eval():
    """Suy luận qua API phải trùng dự đoán dùng khi đánh giá (cùng preprocessor, cùng mô hình)."""
    from ckd_core import gru as R
    from ckd_core.data import load_splits
    te = load_splits()["test"]
    i = int(np.where(~np.isclose(te["eGFR(6M)"], engine.prep.fill_consts["eGFR(6M)"], atol=1e-5)
                     & ~np.isclose(te["eGFR(12M)"], engine.prep.fill_consts["eGFR(12M)"], atol=1e-5))[0][0])
    row = te.iloc[i]
    ref = R.predict(engine.gru, engine.prep.transform(te.iloc[[i]]), engine.prep, engine.use_clinical)[0]
    payload = {"egfr": {"0M": row["eGFR(0M)"], "6M": row["eGFR(6M)"], "12M": row["eGFR(12M)"]},
               "clinical": {c: row[c] for c in C.CLINICAL_COLS}}
    got = [f["egfr"] for f in client.post("/api/predict", json=payload).json()["forecast"]]
    np.testing.assert_allclose(got, ref, atol=1e-4)


@pytest.mark.parametrize("mut", [
    lambda p: p["egfr"].update({"0M": None}),
    lambda p: p["egfr"].update({"0M": "abc"}),
    lambda p: p["egfr"].update({"0M": -5}),
    lambda p: p["egfr"].update({"0M": 999}),
    lambda p: p["clinical"].pop("age"),
    lambda p: p["clinical"].update({"diabetes": 7}),
    lambda p: p["clinical"].update({"etiology of CKD": 9}),
])
def test_bad_inputs_rejected_cleanly(mut):
    import copy
    p = copy.deepcopy(GOOD)
    mut(p)
    r = client.post("/api/predict", json=p)
    assert r.status_code == 422
    assert "Traceback" not in r.text and ".py" not in r.text


def test_non_json_and_csv_errors():
    assert client.post("/api/predict", content=b"not json").status_code == 400
    assert client.post("/api/predict-csv", files={"file": ("x.csv", b"a,b\n1,2\n")}).status_code == 422
    assert client.post("/api/predict-csv", files={"file": ("x.csv", b"")}).status_code == 422


def test_csv_ok():
    te = pd.read_csv(C.SPLIT_FILES["test"]).head(5)
    buf = io.BytesIO(te[["eGFR(0M)", "eGFR(6M)", "eGFR(12M)"] + C.CLINICAL_COLS].to_csv(index=False).encode())
    r = client.post("/api/predict-csv", files={"file": ("t.csv", buf)})
    assert r.status_code == 200 and len(r.json()["rows"]) == 5 and r.json()["rows"][0]["ok"]
