"""GMM phân nhóm quỹ đạo eGFR dựa trên LỊCH SỬ 0-12M (không dùng eGFR tương lai làm đầu vào)."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from . import config as C
from .data import history_features

FEATURE_NAMES = ["eGFR ban đầu (0M)", "eGFR gần nhất (≤12M)", "Độ dốc eGFR 0–12M (mL/ph/1.73m²/năm)"]
K_RANGE = range(2, 7)
COV_TYPES = ["full", "tied", "diag", "spherical"]
MIN_CLUSTER_FRAC = 0.05   # loại cấu hình có cụm < 5% Train (cụm suy biến)


def features(hist: np.ndarray) -> np.ndarray:
    e0, last, slope, _ = history_features(hist)
    return np.stack([e0, last, slope], 1)


def select_and_fit(x_tr, x_va, seed=C.SEED):
    """Fit scaler + GMM trên Train; chọn (K, covariance) theo log-likelihood trung bình trên Validation."""
    scaler = StandardScaler().fit(x_tr)
    a, b = scaler.transform(x_tr), scaler.transform(x_va)
    rows, models = [], {}
    for k, cov in itertools.product(K_RANGE, COV_TYPES):
        g = GaussianMixture(k, covariance_type=cov, n_init=10, reg_covar=1e-4, random_state=seed).fit(a)
        sizes = np.bincount(g.predict(a), minlength=k)
        rows.append(dict(K=k, covariance=cov, train_loglik_mean=g.score(a), train_AIC=g.aic(a),
                         train_BIC=g.bic(a), val_loglik_mean=g.score(b),
                         min_cluster_frac=float(sizes.min() / len(a)),
                         eligible=bool(sizes.min() / len(a) >= MIN_CLUSTER_FRAC)))
        models[(k, cov)] = g
    sel = pd.DataFrame(rows)
    elig = sel[sel.eligible]
    best = elig.sort_values("val_loglik_mean", ascending=False).iloc[0]
    key = (int(best.K), best.covariance)
    return scaler, models[key], sel, key


def stability(x_tr_scaled, k, cov, n_rep=10, seed=C.SEED):
    """Độ ổn định: ARI trung bình giữa các lần fit với khởi tạo ngẫu nhiên khác nhau."""
    labs = [GaussianMixture(k, covariance_type=cov, n_init=1, reg_covar=1e-4, random_state=seed + i)
            .fit(x_tr_scaled).predict(x_tr_scaled) for i in range(n_rep)]
    aris = [adjusted_rand_score(labs[i], labs[j]) for i in range(n_rep) for j in range(i + 1, n_rep)]
    return float(np.mean(aris)), float(np.min(aris))


def order_by_slope(g, scaler):
    """Hoán vị nhãn để Nhóm 1 có độ dốc trung bình thấp nhất (chỉ là thứ tự quy ước, không phải chẩn đoán)."""
    centers = scaler.inverse_transform(g.means_)
    return np.argsort(centers[:, 2])   # perm[new] = old


def assign(g, scaler, perm, x):
    p = g.predict_proba(scaler.transform(x))[:, perm]
    return p.argmax(1), p


def profile(df_masked: pd.DataFrame, labels, probs) -> pd.DataFrame:
    """Mô tả từng nhóm. CKD progression và eGFR tương lai CHỈ dùng để mô tả sau, không dùng để phân nhóm."""
    hist = df_masked[C.HIST_COLS].to_numpy()
    fut = df_masked[C.FUT_COLS].to_numpy()
    e0, last, slope, _ = history_features(hist)
    rows = []
    for k in range(probs.shape[1]):
        m = labels == k
        n = int(m.sum())
        if n == 0:
            rows.append(dict(Nhom=k + 1, N=0))
            continue
        fl = []
        for i in np.where(m)[0]:
            ok = ~np.isnan(fut[i])
            if ok.any():
                fl.append(fut[i][ok][-1] - last[i])
        rows.append(dict(
            Nhom=k + 1, N=n, ty_le=n / len(labels),
            egfr_0M_tb=float(np.nanmean(e0[m])), egfr_gan_nhat_tb=float(np.nanmean(last[m])),
            do_doc_tb=float(slope[m].mean()),
            n_co_theo_doi_tuong_lai=len(fl),
            thay_doi_egfr_tuong_lai_tb=float(np.mean(fl)) if fl else np.nan,
            ty_le_CKD_progression=float(df_masked[C.LABEL_COL].to_numpy()[m].mean()),
            CKD_stage_tb=float(df_masked["CKD_stage"].to_numpy()[m].mean()),
        ))
    return pd.DataFrame(rows)
