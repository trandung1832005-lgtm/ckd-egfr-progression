"""Đọc dữ liệu, kiểm định chất lượng và tiền xử lý (chỉ fit trên Train)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def load_splits() -> dict[str, pd.DataFrame]:
    out = {}
    for name, path in C.SPLIT_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy tập {name}: {path}")
        out[name] = pd.read_csv(path)
    return out


def detect_fill_constants(train: pd.DataFrame) -> dict[str, float]:
    """Tìm giá trị eGFR lặp bất thường trong Train (dấu hiệu điền thiếu bằng trung vị)."""
    consts = {}
    for col in C.EGFR_COLS:
        vc = train[col].round(6).value_counts()
        if vc.iloc[0] >= C.FILL_MIN_COUNT:
            consts[col] = float(vc.index[0])
    return consts


def mask_fill(df: pd.DataFrame, consts: dict[str, float]) -> pd.DataFrame:
    """Đưa các hằng số điền thành NaN (= chưa quan sát)."""
    out = df.copy()
    for col, v in consts.items():
        out.loc[(out[col] - v).abs() < 1e-5, col] = np.nan
    return out


def history_features(hist: np.ndarray):
    """hist: (N,3) có NaN. Trả về egfr0, last_obs, slope (mL/phút/1.73m2 mỗi năm), n_obs."""
    n = hist.shape[0]
    t = np.array(C.HIST_MONTHS, dtype=float)
    last = np.full(n, np.nan)
    slope = np.zeros(n)
    nobs = np.sum(~np.isnan(hist), axis=1)
    for i in range(n):
        ok = ~np.isnan(hist[i])
        if ok.any():
            last[i] = hist[i][ok][-1]
        if ok.sum() >= 2:
            slope[i] = np.polyfit(t[ok], hist[i][ok], 1)[0] * 12.0
    return hist[:, 0], last, slope, nobs


class Preprocessor:
    """Mọi tham số học được đều fit trên Train, dùng lại y nguyên cho Val/Test/suy luận."""

    def fit(self, train: pd.DataFrame) -> "Preprocessor":
        self.fill_consts = detect_fill_constants(train)
        clean = mask_fill(train, self.fill_consts)
        vals = clean[C.EGFR_COLS].to_numpy().ravel()
        vals = vals[~np.isnan(vals)]
        self.egfr_mean, self.egfr_std = float(vals.mean()), float(vals.std())
        self.egfr0_median = float(clean["eGFR(0M)"].median())
        num = self._num_matrix(train)
        self.num_mean, self.num_std = num.mean(0), num.std(0) + 1e-8
        self.etio_levels = sorted(train[C.CLIN_CAT[0]].dropna().unique().tolist())
        self.ranges = {c: (float(train[c].min()), float(train[c].max())) for c in C.CLINICAL_COLS}
        self.ranges.update({c: (float(clean[c].min()), float(clean[c].max())) for c in C.EGFR_COLS})
        return self

    def _num_matrix(self, df):
        m = df[C.CLIN_NUM].astype(float).copy()
        for c in C.CLIN_LOG:
            m[c] = np.log1p(m[c])
        return m.to_numpy()

    def _static(self, df) -> np.ndarray:
        num = (self._num_matrix(df) - self.num_mean) / self.num_std
        b = df[C.CLIN_BIN].astype(float).to_numpy().copy()
        b[:, C.CLIN_BIN.index("gender")] -= 1.0  # 1/2 -> 0/1
        etio = np.stack([(df[C.CLIN_CAT[0]] == lv).astype(float).to_numpy() for lv in self.etio_levels], 1)
        return np.concatenate([num, b, etio], 1).astype(np.float32)

    @property
    def n_static(self) -> int:
        return len(C.CLIN_NUM) + len(C.CLIN_BIN) + len(self.etio_levels)

    def transform(self, df: pd.DataFrame, apply_fill: bool = True) -> dict:
        """apply_fill=True cho CSV huấn luyện (đã điền trung vị); False cho dữ liệu nhập tay."""
        d = mask_fill(df, self.fill_consts) if apply_fill else df.copy()
        eg = d[C.EGFR_COLS].to_numpy(dtype=float)
        hist, fut = eg[:, :C.N_HIST], eg[:, C.N_HIST:]
        n = len(d)
        obs = ~np.isnan(hist)
        ff = np.empty_like(hist)
        dt = np.zeros_like(hist)
        for i in range(n):
            cur, since = self.egfr0_median, 0.0
            for j in range(C.N_HIST):
                if j > 0:
                    since += C.HIST_MONTHS[j] - C.HIST_MONTHS[j - 1]
                if obs[i, j]:
                    cur, since = hist[i, j], 0.0
                ff[i, j], dt[i, j] = cur, since
        sc = (ff - self.egfr_mean) / self.egfr_std
        seq = np.stack([sc, obs.astype(float), dt / 12.0], 2).astype(np.float32)
        return {
            "seq": seq,
            "static": self._static(d),
            "last_scaled": sc[:, -1].astype(np.float32),
            "last_real": ff[:, -1],
            "y": fut,                       # đơn vị thật, NaN = chưa quan sát
            "mask": ~np.isnan(fut),
            "hist": hist,
            "label": d[C.LABEL_COL].to_numpy() if C.LABEL_COL in d else None,
        }


def audit(splits: dict[str, pd.DataFrame]) -> dict:
    """Báo cáo chất lượng dữ liệu (không chỉnh sửa dữ liệu)."""
    prep = Preprocessor().fit(splits["train"])
    rep = {"fill_constants_detected_on_train": prep.fill_consts, "splits": {}}
    for name, df in splits.items():
        clean = mask_fill(df, prep.fill_consts)
        hist = clean[C.HIST_COLS].to_numpy()
        fut = clean[C.FUT_COLS].to_numpy()
        rep["splits"][name] = {
            "rows": int(len(df)), "cols": int(df.shape[1]),
            "duplicate_rows": int(df.duplicated().sum()),
            "nan_in_raw_csv": int(df.isna().sum().sum()),
            "egfr_missing_after_fill_detection": {c: round(float(clean[c].isna().mean()), 4) for c in C.EGFR_COLS},
            "rows_with_no_history": int(np.isnan(hist).all(1).sum()),
            "rows_with_no_future_target": int(np.isnan(fut).all(1).sum()),
            "rows_with_all_targets": int((~np.isnan(fut)).all(1).sum()),
            "label_counts": {str(k): int(v) for k, v in df[C.LABEL_COL].value_counts().items()},
        }
    keys = {n: set(map(tuple, d.round(6).to_numpy())) for n, d in splits.items()}
    rep["identical_rows_across_splits"] = {
        "train_val": len(keys["train"] & keys["val"]),
        "train_test": len(keys["train"] & keys["test"]),
        "val_test": len(keys["val"] & keys["test"]),
    }
    rep["note_patient_id"] = ("Dataset không có cột định danh bệnh nhân: không kiểm tra được trùng bệnh nhân "
                              "giữa các tập, chỉ kiểm tra được trùng nguyên dòng.")
    return rep
