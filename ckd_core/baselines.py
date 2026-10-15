"""Baseline: giữ eGFR gần nhất và hồi quy tuyến tính trên lịch sử."""
import numpy as np
from sklearn.linear_model import LinearRegression

from . import config as C


def persistence(batch) -> np.ndarray:
    return np.repeat(batch["last_real"][:, None], len(C.FUT_COLS), axis=1)


def _x(batch):
    return batch["seq"].reshape(len(batch["seq"]), -1)  # eGFR ffill, cờ quan sát, Δt cho 3 bước


class LinearBaseline:
    """Mỗi mốc dự đoán một LinearRegression, fit trên các dòng Train có mốc đó đã quan sát."""

    def fit(self, batch):
        self.models = []
        for j in range(len(C.FUT_COLS)):
            mk = batch["mask"][:, j]
            self.models.append(LinearRegression().fit(_x(batch)[mk], batch["y"][mk, j]))
        return self

    def predict(self, batch):
        x = _x(batch)
        return np.stack([m.predict(x) for m in self.models], 1)
