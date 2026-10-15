"""Cầu nối tới mô hình GRU/GMM hiện có. Chỉ GỌI `ckd_core.inference.Engine`, không sửa hay huấn luyện lại."""
from __future__ import annotations

import hashlib
import json

from ckd_core import config as C
from ckd_core.guidance import CLUSTER_NOTES, GUIDANCE
from ckd_core.inference import Engine, InputError, ModelNotReady  # noqa: F401  (re-export cho router)

engine = Engine()


def model_version() -> str | None:
    if not engine.ready:
        return None
    h = hashlib.sha256((C.ARTIFACT_DIR / "gru_model.pt").read_bytes()).hexdigest()[:10]
    return f"gru-seed{engine.meta.get('selected_seed')}-{h}"


def status() -> dict:
    return {"ready": engine.ready, "version": model_version(),
            "torch": engine.meta.get("versions", {}).get("torch") if engine.ready else None,
            "gmm": engine.meta.get("gmm") if engine.ready else None}


def enrich(result: dict) -> dict:
    """Thêm hướng dẫn và mô tả nhóm (suy từ kết quả đã lưu, không lưu trùng văn bản)."""
    stage = result["final_stage"]
    out = dict(result)
    out["guidance"] = {"stage": stage, **GUIDANCE[stage]}
    out["gmm"] = {**result["gmm"], "note": CLUSTER_NOTES.get(result["gmm"]["name"], "")}
    return out


def dumps(result: dict) -> str:
    keep = {k: result[k] for k in ("history", "forecast", "final_stage", "warnings")}
    g = result["gmm"]
    keep["gmm"] = {k: g[k] for k in ("cluster", "name", "names", "probabilities", "features", "total_slope",
                                     "history_slope", "forecast_slope")}
    return json.dumps(keep, ensure_ascii=False)
