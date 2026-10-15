"""Suy luận bằng artifact đã huấn luyện. Không huấn luyện lại, không tạo kết quả giả."""
from __future__ import annotations

import json
import math

import joblib
import numpy as np
import pandas as pd
import torch

from . import config as C
from . import gmm as G
from . import gru as R

EGFR_KEYS = {"0M": "eGFR(0M)", "6M": "eGFR(6M)", "12M": "eGFR(12M)"}
HARD_EGFR = (0.0, 200.0)


class InputError(ValueError):
    """Lỗi do dữ liệu người dùng nhập (an toàn để hiển thị)."""


class ModelNotReady(RuntimeError):
    pass


class Engine:
    def __init__(self):
        self.ready = False
        self.error = None
        try:
            self.meta = json.loads((C.ARTIFACT_DIR / "meta.json").read_text("utf-8"))
            self.prep = joblib.load(C.ARTIFACT_DIR / "preprocessor.joblib")
            ck = torch.load(C.ARTIFACT_DIR / "gru_model.pt", map_location="cpu", weights_only=False)
            hp = ck["hp"]
            self.use_clinical = hp["use_clinical"]
            self.gru = R.GRUForecaster(ck["n_static"], hp["hidden"], hp["layers"], hp["dropout"],
                                       hp["static_dim"], hp["head_dim"])
            self.gru.load_state_dict(ck["state_dict"])
            self.gru.eval()
            g = joblib.load(C.ARTIFACT_DIR / "gmm_model.joblib")
            self.scaler, self.gmm, self.perm, self.K = g["scaler"], g["gmm"], g["perm"], g["K"]
            prof = pd.read_csv(C.REPORT_DIR / "gmm_cluster_profile.csv")
            self.profile = prof[prof.Tap == "train"].set_index("Nhom")
            self.ready = True
        except Exception as e:  # noqa: BLE001 - trạng thái "chưa sẵn sàng" được báo cho giao diện
            self.error = f"{type(e).__name__}"

    # ---------- kiểm tra đầu vào ----------
    @staticmethod
    def _num(v, name):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        try:
            x = float(v)
        except (TypeError, ValueError):
            raise InputError(f"'{name}' phải là số.")
        if not math.isfinite(x):
            raise InputError(f"'{name}' không hợp lệ.")
        return x

    def _row(self, payload: dict):
        eg = payload.get("egfr") or {}
        row, warns = {}, []
        for k, col in EGFR_KEYS.items():
            v = self._num(eg.get(k), f"eGFR {k}")
            if v is not None and not (HARD_EGFR[0] < v <= HARD_EGFR[1]):
                raise InputError(f"eGFR {k} phải nằm trong (0, 200].")
            row[col] = np.nan if v is None else v
        if np.isnan(row["eGFR(0M)"]):
            raise InputError("Cần nhập eGFR tại mốc 0M (mốc 6M/12M có thể bỏ trống).")
        for col in C.FUT_COLS:
            row[col] = np.nan
        clin = payload.get("clinical") or {}
        for col in C.CLINICAL_COLS:
            lo, hi = self.prep.ranges[col]
            if self.use_clinical:
                v = self._num(clin.get(col), col)
                if v is None:
                    raise InputError(f"Thiếu biến lâm sàng '{col}'.")
                if col in C.CLIN_CAT:
                    allowed = {float(x) for x in self.prep.etio_levels}
                elif col in C.CLIN_BIN:
                    allowed = {float(lo), float(hi)}  # gender: 1/2; các biến còn lại: 0/1
                else:
                    allowed = None
                if allowed is not None and v not in allowed:
                    raise InputError(f"'{col}' chỉ nhận một trong các giá trị {sorted(allowed)}.")
                if col in C.CLIN_NUM and (v < 0):
                    raise InputError(f"'{col}' không được âm.")
                if col in C.CLIN_NUM and not (lo <= v <= hi):
                    warns.append(f"'{col}'={v:g} nằm ngoài khoảng dữ liệu huấn luyện [{lo:g}, {hi:g}]: kết quả kém tin cậy.")
                row[col] = v
            else:
                row[col] = (lo + hi) / 2  # không dùng trong mô hình, chỉ để đủ cột
        for k, col in EGFR_KEYS.items():
            if not np.isnan(row[col]):
                lo, hi = self.prep.ranges[col]
                if not (lo <= row[col] <= hi):
                    warns.append(f"eGFR {k}={row[col]:g} nằm ngoài khoảng dữ liệu huấn luyện [{lo:.1f}, {hi:.1f}].")
        return row, warns

    # ---------- suy luận ----------
    def predict(self, payload: dict) -> dict:
        if not self.ready:
            raise ModelNotReady("Mô hình chưa sẵn sàng: chưa có artifact đã huấn luyện.")
        row, warns = self._row(payload)
        df = pd.DataFrame([row])
        b = self.prep.transform(df, apply_fill=False)
        pred = R.predict(self.gru, b, self.prep, self.use_clinical)[0]
        feats = G.features(b["hist"])
        z = self.scaler.transform(feats)
        probs = self.gmm.predict_proba(z)[:, self.perm][0]
        k = int(probs.argmax())
        n_obs = int((~np.isnan(b["hist"][0])).sum())
        if n_obs < 2:
            warns.append("Chỉ có 1 mốc eGFR lịch sử: độ dốc được đặt = 0, phân nhóm GMM kém tin cậy.")
        prof = self.profile.loc[k + 1].to_dict() if (k + 1) in self.profile.index else {}
        return {
            "history": {m: (None if np.isnan(row[c]) else float(row[c])) for m, c in EGFR_KEYS.items()},
            "forecast": [{"month": m, "egfr": float(p)} for m, p in zip(C.FUT_MONTHS, pred)],
            "gmm": {
                "cluster": k + 1, "probabilities": [float(p) for p in probs],
                "features": {n: float(v) for n, v in zip(G.FEATURE_NAMES, feats[0])},
                "profile": {kk: (None if (isinstance(vv, float) and math.isnan(vv)) else vv) for kk, vv in prof.items()},
            },
            "warnings": warns,
        }

    def predict_table(self, df: pd.DataFrame) -> list[dict]:
        out = []
        for i, r in df.reset_index(drop=True).iterrows():
            payload = {"egfr": {k: r.get(c) for k, c in EGFR_KEYS.items()},
                       "clinical": {c: r.get(c) for c in C.CLINICAL_COLS}}
            try:
                res = self.predict(payload)
                out.append({"row": i + 1, "ok": True, **{f"eGFR_{f['month']}M_du_doan": round(f["egfr"], 2) for f in res["forecast"]},
                            "nhom_gmm": res["gmm"]["cluster"], "canh_bao": "; ".join(res["warnings"])})
            except InputError as e:
                out.append({"row": i + 1, "ok": False, "loi": str(e)})
        return out
