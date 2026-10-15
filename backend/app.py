"""API suy luận (FastAPI). Chạy:  uvicorn backend.app:app --port 8000

Biến môi trường:
  ALLOWED_ORIGINS  danh sách origin được phép gọi API, phân tách bằng dấu phẩy (mặc định: *)
"""
import io
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from ckd_core import config as C  # noqa: E402
from ckd_core.inference import Engine, InputError, ModelNotReady  # noqa: E402

log = logging.getLogger("ckd-api")
app = FastAPI(title="CKD eGFR – GRU & GMM", docs_url="/api/docs", openapi_url="/api/openapi.json")
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

engine = Engine()
MAX_UPLOAD = 2 * 1024 * 1024
MAX_ROWS = 2000


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("Lỗi không lường trước")          # chi tiết chỉ ghi log phía server
    return JSONResponse({"error": "Lỗi nội bộ máy chủ. Vui lòng thử lại sau."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok" if engine.ready else "model_not_ready", "model_ready": engine.ready,
            "detail": None if engine.ready else "Chưa nạp được artifact đã huấn luyện (xem README, mục Huấn luyện)."}


def _need_ready():
    if not engine.ready:
        raise HTTPException(503, "Mô hình chưa sẵn sàng: chưa có artifact đã huấn luyện.")


def _read_csv(name):
    p = C.REPORT_DIR / name
    if not p.exists():
        return []
    df = pd.read_csv(p)
    return df.astype(object).where(df.notna(), None).to_dict("records")  # NaN -> null (JSON hợp lệ)


@app.get("/api/meta")
def meta():
    _need_ready()
    m = engine.meta
    return {
        "history_months": m["history_months"], "future_months": m["future_months"], "use_clinical": m["use_clinical"],
        "clinical_columns": m["clinical_columns"] if m["use_clinical"] else [],
        "input_ranges": m["input_ranges"], "etiology_levels": m["etiology_levels"],
        "hyperparameters": m["hyperparameters"], "gmm": m["gmm"], "rows": m["rows"],
    }


@app.get("/api/results")
def results():
    _need_ready()
    audit = C.REPORT_DIR / "data_audit.json"
    return {
        "regression": _read_csv("regression_metrics.csv"),
        "gru_seeds": _read_csv("gru_seed_variability.csv"),
        "gmm_metrics": _read_csv("gmm_metrics.csv"),
        "gmm_selection": _read_csv("gmm_model_selection.csv"),
        "gmm_profile": _read_csv("gmm_cluster_profile.csv"),
        "gmm_trajectories": _read_csv("gmm_cluster_trajectories.csv"),
        "data_audit": json.loads(audit.read_text("utf-8")) if audit.exists() else None,
    }


@app.post("/api/predict")
async def predict(request: Request):
    _need_ready()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Dữ liệu gửi lên không phải JSON hợp lệ.")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Dữ liệu gửi lên không hợp lệ.")
    try:
        return engine.predict(payload)
    except InputError as e:
        raise HTTPException(422, str(e))
    except ModelNotReady as e:
        raise HTTPException(503, str(e))


@app.post("/api/predict-csv")
async def predict_csv(file: UploadFile = File(...)):
    _need_ready()
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "File quá lớn (tối đa 2 MB).")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        raise HTTPException(422, "Không đọc được file CSV.")
    if len(df) == 0 or len(df) > MAX_ROWS:
        raise HTTPException(422, f"File phải có từ 1 đến {MAX_ROWS} dòng.")
    need = ["eGFR(0M)"] + (C.CLINICAL_COLS if engine.use_clinical else [])
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise HTTPException(422, f"File thiếu cột: {', '.join(missing)}.")
    return {"rows": engine.predict_table(df)}


web_dir = ROOT / "web"
if web_dir.exists():   # chạy cục bộ: một lệnh phục vụ cả giao diện lẫn API
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
