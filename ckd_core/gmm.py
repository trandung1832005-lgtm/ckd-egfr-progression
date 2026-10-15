"""GMM (K=3) phân nhóm xu hướng eGFR: kết hợp tiền sử quan sát (0–12M) với eGFR do GRU dự đoán (18–36M).

Giai đoạn 2 của pipeline: đầu vào là *dự đoán của GRU*, không bao giờ là eGFR tương lai thật.
Tên nhóm gán theo độ dốc trung bình của quỹ đạo (lên dần = Cải thiện, ngang = Ổn định, xuống dần =
Chuyển biến xấu). Đó là nhãn tương đối theo mẫu, không phải chẩn đoán.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from . import config as C

class ClippedScaler:
    """Cắt ngoại lai theo phân vị 5–95% của Train rồi chuẩn hóa. Mọi tham số chỉ fit trên Train.

    Cần thiết vì độ dốc có đuôi dài (vài bệnh nhân > +10/năm do nhiễu đo); không cắt thì GMM
    dành riêng một nhóm cho vài ngoại lai thay vì chia xu hướng chung."""

    def __init__(self, q=(5, 95)):
        self.q = q

    def fit(self, x):
        self.lo, self.hi = np.percentile(x, self.q, axis=0)
        self.sc = StandardScaler().fit(np.clip(x, self.lo, self.hi))
        return self

    def transform(self, x):
        return self.sc.transform(np.clip(x, self.lo, self.hi))


K = 3
CLUSTER_NAMES = ["Chuyển biến xấu", "Ổn định", "Cải thiện"]   # thứ tự theo độ dốc tăng dần
FEATURE_NAMES = ["Độ dốc eGFR toàn quỹ đạo: đã đo + GRU dự đoán (mL/ph/1.73m²/năm)"]
COV_TYPES = ["full", "tied", "diag", "spherical"]
MIN_CLUSTER_FRAC = 0.05   # loại cấu hình có cụm < 5% Train (cụm suy biến)


def _slope(t, y) -> float:
    return float(np.polyfit(t, y, 1)[0] * 12.0) if len(t) >= 2 else 0.0


def trajectory_features(hist: np.ndarray, pred: np.ndarray):
    """hist (N,3) có NaN; pred (N,4) do GRU dự đoán.

    Trả về (X (N,1), detail (N,2)).
      X       = độ dốc OLS của toàn quỹ đạo [các mốc đã đo + 4 mốc GRU dự đoán] (mL/ph/1.73m²/năm); đầu vào GMM.
                Tính được cho mọi bệnh nhân, không cần giả định kể cả khi chỉ có 1 mốc đo.
      detail  = [độ dốc lịch sử đã đo (NaN nếu < 2 mốc), độ dốc dự báo neo tại lần đo cuối]; chỉ để mô tả.
    """
    th_all, tf = np.array(C.HIST_MONTHS, float), np.array(C.FUT_MONTHS, float)
    x = np.zeros((len(hist), 1))
    detail = np.full((len(hist), 2), np.nan)
    for i in range(len(hist)):
        ok = ~np.isnan(hist[i])
        th, yh = th_all[ok], hist[i][ok]
        x[i, 0] = _slope(np.r_[th, tf], np.r_[yh, pred[i]])
        if ok.sum() >= 2:
            detail[i, 0] = _slope(th, yh)
        detail[i, 1] = _slope(np.r_[th[-1], tf], np.r_[yh[-1], pred[i]])
    return x, detail


def select_and_fit(x_tr, x_va, seed=C.SEED):
    """K cố định = 3. Fit scaler + GMM trên Train; chọn loại covariance theo log-likelihood trung bình trên Validation."""
    scaler = ClippedScaler().fit(x_tr)
    a, b = scaler.transform(x_tr), scaler.transform(x_va)
    rows, models = [], {}
    for cov in COV_TYPES:
        g = GaussianMixture(K, covariance_type=cov, n_init=10, reg_covar=1e-4, random_state=seed).fit(a)
        frac = np.bincount(g.predict(a), minlength=K).min() / len(a)
        rows.append(dict(K=K, covariance=cov, train_loglik_mean=g.score(a), train_AIC=g.aic(a), train_BIC=g.bic(a),
                         val_loglik_mean=g.score(b), min_cluster_frac=float(frac), eligible=bool(frac >= MIN_CLUSTER_FRAC)))
        models[cov] = g
    sel = pd.DataFrame(rows)
    pool = sel[sel.eligible] if sel.eligible.any() else sel
    cov = pool.sort_values("val_loglik_mean", ascending=False).iloc[0].covariance
    return scaler, models[cov], sel, cov


def stability(x_tr_scaled, cov, n_rep=10, seed=C.SEED):
    """ARI trung bình/nhỏ nhất giữa các lần fit với khởi tạo ngẫu nhiên khác nhau."""
    labs = [GaussianMixture(K, covariance_type=cov, n_init=1, reg_covar=1e-4, random_state=seed + i)
            .fit(x_tr_scaled).predict(x_tr_scaled) for i in range(n_rep)]
    aris = [adjusted_rand_score(labs[i], labs[j]) for i in range(n_rep) for j in range(i + 1, n_rep)]
    return float(np.mean(aris)), float(np.min(aris))


def order_by_total_slope(g, scaler, x_tr):
    """perm[new] = old, sao cho nhóm 0 có độ dốc trung bình thấp nhất (trên Train)."""
    lab = g.predict(scaler.transform(x_tr))
    means = [x_tr[lab == k, 0].mean() if (lab == k).any() else np.inf for k in range(K)]
    return np.argsort(means)


def assign(g, scaler, perm, x):
    p = g.predict_proba(scaler.transform(x))[:, perm]
    return p.argmax(1), p


def profile(df_masked: pd.DataFrame, labels, x, detail) -> pd.DataFrame:
    """Mô tả nhóm. eGFR tương lai thật và CKD progression chỉ để kiểm tra/mô tả SAU khi phân nhóm."""
    hist = df_masked[C.HIST_COLS].to_numpy()
    fut = df_masked[C.FUT_COLS].to_numpy()
    last = np.array([h[~np.isnan(h)][-1] for h in hist])
    rows = []
    for k in range(K):
        m = labels == k
        n = int(m.sum())
        row = dict(Nhom=k + 1, Ten=CLUSTER_NAMES[k], N=n, ty_le=n / len(labels))
        if n:
            ch = [fut[i][~np.isnan(fut[i])][-1] - last[i] for i in np.where(m)[0] if (~np.isnan(fut[i])).any()]
            row.update(egfr_0M_tb=float(np.nanmean(hist[m, 0])), do_doc_tong_tb=float(x[m, 0].mean()),
                       do_doc_lich_su_tb=float(np.nanmean(detail[m, 0])) if (~np.isnan(detail[m, 0])).any() else np.nan,
                       n_co_ca_2_moc_lich_su=int((~np.isnan(detail[m, 0])).sum()),
                       do_doc_du_bao_tb=float(detail[m, 1].mean()),
                       n_co_theo_doi_tuong_lai=len(ch),
                       thay_doi_egfr_thuc_te_tb=float(np.mean(ch)) if ch else np.nan,
                       ty_le_CKD_progression=float(df_masked[C.LABEL_COL].to_numpy()[m].mean()),
                       CKD_stage_tb=float(df_masked["CKD_stage"].to_numpy()[m].mean()))
        rows.append(row)
    return pd.DataFrame(rows)
