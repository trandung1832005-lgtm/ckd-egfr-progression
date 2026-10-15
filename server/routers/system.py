from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import model_service as M
from ..deps import current_user
from ..models import User

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    """Kiểm tra sống cho nền tảng triển khai; không tiết lộ chi tiết nội bộ."""
    return {"status": "ok"}


@router.get("/models/spec")
def models_spec(user: User = Depends(current_user)):
    """Mô tả đầu vào mô hình (khoảng giá trị thường gặp, mã nguyên nhân) để giao diện dựng form và cảnh báo."""
    if not M.engine.ready:
        raise HTTPException(503, "Mô hình chưa sẵn sàng.")
    m = M.engine.meta
    uc = m["use_clinical"]
    return {"future_months": m["future_months"], "use_clinical": uc,
            "clinical_columns": m["clinical_columns"] if uc else [],
            "input_ranges": m["input_ranges"], "etiology_levels": m["etiology_levels"]}


@router.get("/models/status")
def models_status(user: User = Depends(current_user)):
    s = M.status()
    if user.role == "admin":
        return s
    return {"ready": s["ready"]}          # vai trò khác chỉ cần biết mô hình có sẵn sàng hay không
