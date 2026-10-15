"""Huấn luyện + đánh giá toàn bộ pipeline: baseline, GRU, GMM.

Quy tắc: mọi lựa chọn (siêu tham số, checkpoint, cấu hình GMM) chỉ dựa trên Train/Validation.
Test chỉ được tính SAU KHI mô hình đã cố định.

    python scripts/train_all.py            # đầy đủ (tìm siêu tham số ~ vài phút trên CPU)
    python scripts/train_all.py --trials 6 # chạy nhanh để thử
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib  # noqa: E402
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import sklearn  # noqa: E402

from ckd_core import config as C  # noqa: E402
from ckd_core import gmm as G  # noqa: E402
from ckd_core import gru as R  # noqa: E402
from ckd_core.baselines import LinearBaseline, persistence  # noqa: E402
from ckd_core.data import Preprocessor, audit, load_splits, mask_fill  # noqa: E402
from ckd_core.metrics import regression_table  # noqa: E402

log = logging.getLogger("train")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    t0 = time.time()
    for d in (C.ARTIFACT_DIR, C.REPORT_DIR, C.FIG_DIR, C.PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(C.REPORT_DIR / "train_log.txt", "w", "utf-8")])

    splits = load_splits()
    (C.REPORT_DIR / "data_audit.json").write_text(json.dumps(audit(splits), indent=2, ensure_ascii=False), "utf-8")
    prep = Preprocessor().fit(splits["train"])          # CHỈ fit trên Train
    B = {k: prep.transform(v) for k, v in splits.items()}
    log.info("Hằng số điền thiếu phát hiện trên Train: %s", prep.fill_consts)
    for k in B:
        np.savez_compressed(C.PROCESSED_DIR / f"{k}_sequences.npz", **{a: b for a, b in B[k].items() if a != "label" or b is not None})
        log.info("%s: %d dòng, %d dòng có >=1 mốc đích quan sát (dùng để tính chỉ số)", k, len(B[k]["seq"]),
                 int(B[k]["mask"].any(1).sum()))

    # ---------------- Baseline ----------------
    lin = LinearBaseline().fit(B["train"])
    base_preds = {
        "Baseline: giữ eGFR gần nhất": {k: persistence(B[k]) for k in B},
        "Baseline: Linear Regression": {k: np.clip(lin.predict(B[k]), 0, None) for k in B},
    }

    # ---------------- GRU: tìm siêu tham số trên Validation ----------------
    configs = R.sample_configs(args.trials, C.SEED)
    search = []
    for i, hp in enumerate(configs):
        _, info = R.train_one(hp, prep, B["train"], B["val"], seed=0)
        search.append({**hp, "val_mae": info["best_val_mae"], "best_epoch": info["best_epoch"]})
        log.info("[%d/%d] val_MAE=%.3f ep=%d %s", i + 1, len(configs), info["best_val_mae"], info["best_epoch"], hp)
    sdf = pd.DataFrame(search).sort_values("val_mae").reset_index(drop=True)
    sdf.to_csv(C.REPORT_DIR / "gru_hyperparameter_search.csv", index=False)
    best_hp = {k: (v.item() if hasattr(v, "item") else v) for k, v in sdf.iloc[0].drop(["val_mae", "best_epoch"]).items()}
    log.info("Cấu hình tốt nhất theo Validation: %s", best_hp)

    # ---------------- GRU: huấn luyện lại nhiều seed, chọn seed theo Validation ----------------
    runs = []
    for s in range(args.seeds):
        m, info = R.train_one(best_hp, prep, B["train"], B["val"], seed=100 + s)
        runs.append((m, info, 100 + s))
        log.info("seed %d: val_MAE=%.3f", 100 + s, info["best_val_mae"])
    bi = int(np.argmin([r[1]["best_val_mae"] for r in runs]))
    model, info, seed_used = runs[bi]
    uc = best_hp["use_clinical"]

    pred = {k: R.predict(model, B[k], prep, uc) for k in B}
    tables = []
    for name, pp in [("GRU", pred)] + list(base_preds.items()):
        for sp in ("val", "test"):
            tables.append(regression_table(B[sp]["y"], pp[sp], B[sp]["mask"], name, sp))
    reg = pd.concat(tables, ignore_index=True)
    reg.to_csv(C.REPORT_DIR / "regression_metrics.csv", index=False, encoding="utf-8-sig")

    # độ biến thiên theo seed (chỉ báo cáo, không dùng để chọn)
    seed_rows = []
    for m, inf, s in runs:
        pv, pt = R.predict(m, B["val"], prep, uc), R.predict(m, B["test"], prep, uc)
        seed_rows.append(dict(seed=s, val_MAE=R.masked_mae(pv, B["val"]), test_MAE=R.masked_mae(pt, B["test"]),
                              selected=(s == seed_used)))
    pd.DataFrame(seed_rows).to_csv(C.REPORT_DIR / "gru_seed_variability.csv", index=False)

    for sp in ("val", "test"):
        rows = []
        for i in range(len(pred[sp])):
            for j, mo in enumerate(C.FUT_MONTHS):
                if B[sp]["mask"][i, j]:
                    rows.append(dict(row_index=i, moc=f"{mo}M", egfr_thuc=B[sp]["y"][i, j], egfr_du_doan=pred[sp][i, j]))
        pd.DataFrame(rows).to_csv(C.REPORT_DIR / f"predictions_{sp}.csv", index=False)

    # ---------------- GMM (giai đoạn 2: dựa trên dự đoán của GRU) ----------------
    masked = {k: mask_fill(v, prep.fill_consts) for k, v in splits.items()}
    FT = {k: G.trajectory_features(B[k]["hist"], pred[k]) for k in B}
    X = {k: FT[k][0] for k in B}
    DET = {k: FT[k][1] for k in B}
    K = G.K
    scaler, gm, sel, cov = G.select_and_fit(X["train"], X["val"])
    sel.to_csv(C.REPORT_DIR / "gmm_model_selection.csv", index=False)
    perm = G.order_by_total_slope(gm, scaler, X["train"])
    ari_mean, ari_min = G.stability(scaler.transform(X["train"]), cov)
    prof, gmm_rows, assign_all = [], [], {}
    for k in B:
        lab, pr = G.assign(gm, scaler, perm, X[k])
        assign_all[k] = (lab, pr)
        p = G.profile(masked[k], lab, X[k], DET[k])
        p.insert(0, "Tap", k)
        prof.append(p)
        z = scaler.transform(X[k])
        gmm_rows.append(dict(Tap=k, N=len(z), loglik_mean=gm.score(z), AIC=gm.aic(z), BIC=gm.bic(z)))
    profile_df = pd.concat(prof)
    profile_df.to_csv(C.REPORT_DIR / "gmm_cluster_profile.csv", index=False, encoding="utf-8-sig")
    gdf = pd.DataFrame(gmm_rows)
    gdf["K"], gdf["covariance"], gdf["ARI_on_restart_mean"], gdf["ARI_on_restart_min"] = K, cov, ari_mean, ari_min
    gdf.to_csv(C.REPORT_DIR / "gmm_metrics.csv", index=False)
    log.info("GMM K=%d, covariance=%s (chọn theo log-likelihood Validation); ARI khởi tạo lại: mean=%.3f min=%.3f",
             K, cov, ari_mean, ari_min)
    for _, r in profile_df[profile_df.Tap == "train"].iterrows():
        log.info("Train nhóm %d %-16s N=%d độ dốc tổng TB=%.2f", r.Nhom, r.Ten, r.N, r.do_doc_tong_tb)

    # ---------------- Lưu artifact ----------------
    torch.save({"state_dict": model.state_dict(), "hp": best_hp, "n_static": prep.n_static if uc else 0,
                "seed": seed_used}, C.ARTIFACT_DIR / "gru_model.pt")
    joblib.dump(prep, C.ARTIFACT_DIR / "preprocessor.joblib")
    joblib.dump({"scaler": scaler, "gmm": gm, "perm": perm, "K": K, "covariance": cov,
                 "names": G.CLUSTER_NAMES}, C.ARTIFACT_DIR / "gmm_model.joblib")
    meta = {
        "versions": {"torch": torch.__version__, "sklearn": sklearn.__version__, "numpy": np.__version__},
        "history_months": C.HIST_MONTHS, "future_months": C.FUT_MONTHS,
        "use_clinical": uc, "hyperparameters": best_hp, "selected_seed": seed_used,
        "best_epoch": info["best_epoch"], "n_search_trials": len(configs),
        "gmm": {"K": K, "covariance": cov, "features": G.FEATURE_NAMES, "cluster_names": G.CLUSTER_NAMES},
        "clinical_columns": C.CLINICAL_COLS, "input_ranges": prep.ranges,
        "etiology_levels": prep.etio_levels, "fill_constants": prep.fill_consts,
        "rows": {k: int(len(v)) for k, v in splits.items()},
    }
    (C.ARTIFACT_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")

    # quỹ đạo trung bình theo nhóm: đã đo (lịch sử) / GRU dự đoán / thực tế tương lai (chỉ để đối chiếu)
    traj = []
    for sp in B:
        lb = assign_all[sp][0]
        hist, fut = B[sp]["hist"], B[sp]["y"]
        for k_ in range(K):
            m = lb == k_
            def add(kind, mo, v):
                v = v[~np.isnan(v)]
                traj.append(dict(Tap=sp, Nhom=k_ + 1, Ten=G.CLUSTER_NAMES[k_], loai=kind, thang=mo, n=len(v),
                                 egfr_tb=float(v.mean()) if len(v) else None))
            for j, mo in enumerate(C.HIST_MONTHS):
                add("da_do", mo, hist[m, j])
            for j, mo in enumerate(C.FUT_MONTHS):
                add("du_doan_GRU", mo, pred[sp][m, j])
                add("thuc_te", mo, fut[m, j])
    pd.DataFrame(traj).to_csv(C.REPORT_DIR / "gmm_cluster_trajectories.csv", index=False)

    # ---------------- Biểu đồ ----------------
    plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": .3})
    h = info["history"]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].plot(h["train_loss"]); ax[0].set(title="Loss huấn luyện (Huber, thang chuẩn hóa)", xlabel="Epoch")
    ax[1].plot(h["val_mae"]); ax[1].axvline(info["best_epoch"], ls="--", c="r", label="checkpoint tốt nhất")
    ax[1].set(title="MAE Validation (mL/ph/1.73m²)", xlabel="Epoch"); ax[1].legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "01_loss_curves.png"); plt.close(fig)

    fig, axs = plt.subplots(1, 4, figsize=(15, 3.8))
    for j, mo in enumerate(C.FUT_MONTHS):
        mk = B["test"]["mask"][:, j]
        y, p = B["test"]["y"][mk, j], pred["test"][mk, j]
        axs[j].scatter(y, p, s=14, alpha=.6)
        lim = [0, max(y.max(), p.max()) * 1.05]
        axs[j].plot(lim, lim, "r--"); axs[j].set(title=f"Test – {mo}M (n={mk.sum()})", xlabel="eGFR thực", ylabel="eGFR dự đoán")
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "02_actual_vs_predicted_test.png"); plt.close(fig)

    t = reg[(reg.Tap == "test") & (reg.Moc != "Tổng thể")]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    w = 0.27
    for i, (name, g) in enumerate(t.groupby("Mo_hinh", sort=False)):
        ax.bar(np.arange(4) + i * w, g.MAE.values, w, label=name)
    ax.set_xticks(np.arange(4) + w); ax.set_xticklabels([f"{m}M" for m in C.FUT_MONTHS])
    ax.set(title="MAE trên Test theo mốc dự đoán", ylabel="MAE"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "03_mae_by_horizon_test.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.bar(sel.covariance, sel.val_loglik_mean, color=["#0b7a75" if c == cov else "#9fb0be" for c in sel.covariance])
    ax.set(title="GMM K=3: log-likelihood trung bình trên Validation", ylabel="log-likelihood")
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "04_gmm_covariance_selection.png"); plt.close(fig)

    tj = pd.DataFrame(traj)
    tj = tj[tj.Tap == "test"]
    colors = ["#b3261e", "#6b7280", "#1b7f3b"]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for k_ in range(K):
        d = tj[tj.Nhom == k_ + 1]
        n_k = int(d[d.loai == "da_do"].n.max())
        a_ = d[d.loai == "da_do"]; b_ = d[d.loai == "du_doan_GRU"]; c_ = d[(d.loai == "thuc_te") & (d.n >= 5)]
        ax.plot(a_.thang, a_.egfr_tb, "o-", c=colors[k_], label=f"{G.CLUSTER_NAMES[k_]} (n={n_k})")
        ax.plot([a_.thang.iloc[-1], *b_.thang], [a_.egfr_tb.iloc[-1], *b_.egfr_tb], "o--", c=colors[k_])
        ax.plot(c_.thang, c_.egfr_tb, "x:", c=colors[k_], alpha=.7)
    ax.axvline(12.5, ls=":", c="k")
    ax.set(title="eGFR trung bình theo nhóm (Test): liền = đã đo, đứt = GRU dự đoán, chấm × = thực tế (n≥5)",
           xlabel="Tháng", ylabel="eGFR")
    ax.title.set_fontsize(9); ax.legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "05_gmm_cluster_trajectories.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    lab = assign_all["train"][0]
    bins = np.linspace(np.percentile(X["train"][:, 0], 1), np.percentile(X["train"][:, 0], 99), 40)
    for k_ in range(K):
        ax.hist(X["train"][lab == k_, 0], bins=bins, alpha=.65, color=colors[k_], label=f"{G.CLUSTER_NAMES[k_]} (n={int((lab==k_).sum())})")
    ax.set(title="Phân bố độ dốc eGFR toàn quỹ đạo theo nhóm GMM (Train)", xlabel=G.FEATURE_NAMES[0], ylabel="Số bệnh nhân")
    ax.title.set_fontsize(10); ax.legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "06_gmm_slope_distribution.png"); plt.close(fig)

    log.info("XONG sau %.1f phút", (time.time() - t0) / 60)


if __name__ == "__main__":
    main()
