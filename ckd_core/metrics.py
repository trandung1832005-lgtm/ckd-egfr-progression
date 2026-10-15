"""Chỉ số hồi quy tính trên giá trị eGFR thật, chỉ ở các mốc đã quan sát."""
import numpy as np
import pandas as pd

from . import config as C


def _m(y, p):
    if len(y) == 0:
        return dict(N=0, MAE=np.nan, RMSE=np.nan, R2=np.nan)
    err = p - y
    sst = np.sum((y - y.mean()) ** 2)
    return dict(N=int(len(y)), MAE=float(np.abs(err).mean()), RMSE=float(np.sqrt((err ** 2).mean())),
                R2=float(1 - np.sum(err ** 2) / sst) if sst > 0 else np.nan)


def regression_table(y, pred, mask, label: str, split: str) -> pd.DataFrame:
    rows = [dict(Moc="Tổng thể", **_m(y[mask], pred[mask]))]
    for j, mo in enumerate(C.FUT_MONTHS):
        mk = mask[:, j]
        rows.append(dict(Moc=f"{mo}M", **_m(y[mk, j], pred[mk, j])))
    df = pd.DataFrame(rows)
    df.insert(0, "Tap", split)
    df.insert(0, "Mo_hinh", label)
    return df
