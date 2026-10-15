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

    # ---------------- GMM ----------------
    masked = {k: mask_fill(v, prep.fill_consts) for k, v in splits.items()}
    X = {k: G.features(B[k]["hist"]) for k in B}
    scaler, gm, sel, (K, cov) = G.select_and_fit(X["train"], X["val"])
    sel.to_csv(C.REPORT_DIR / "gmm_model_selection.csv", index=False)
    perm = G.order_by_slope(gm, scaler)
    ari_mean, ari_min = G.stability(scaler.transform(X["train"]), K, cov)
    prof, gmm_rows, assign_all = [], [], {}
    for k in B:
        lab, pr = G.assign(gm, scaler, perm, X[k])
        assign_all[k] = (lab, pr)
        p = G.profile(masked[k], lab, pr)
        p.insert(0, "Tap", k)
        prof.append(p)
        z = scaler.transform(X[k])
        gmm_rows.append(dict(Tap=k, N=len(z), loglik_mean=gm.score(z), AIC=gm.aic(z), BIC=gm.bic(z)))
    pd.concat(prof).to_csv(C.REPORT_DIR / "gmm_cluster_profile.csv", index=False, encoding="utf-8-sig")
    gdf = pd.DataFrame(gmm_rows)
    gdf["K"], gdf["covariance"], gdf["ARI_on_restart_mean"], gdf["ARI_on_restart_min"] = K, cov, ari_mean, ari_min
    gdf.to_csv(C.REPORT_DIR / "gmm_metrics.csv", index=False)
    log.info("GMM chọn K=%d cov=%s (theo log-likelihood Validation); ARI khởi tạo lại: mean=%.3f min=%.3f", K, cov, ari_mean, ari_min)

    # ---------------- Lưu artifact ----------------
    torch.save({"state_dict": model.state_dict(), "hp": best_hp, "n_static": prep.n_static if uc else 0,
                "seed": seed_used}, C.ARTIFACT_DIR / "gru_model.pt")
    joblib.dump(prep, C.ARTIFACT_DIR / "preprocessor.joblib")
    joblib.dump({"scaler": scaler, "gmm": gm, "perm": perm, "K": K, "covariance": cov}, C.ARTIFACT_DIR / "gmm_model.joblib")
    cl = {lab: {"mean": X["train"][assign_all["train"][0] == lab].mean(0).tolist()} for lab in range(K)}
    meta = {
        "versions": {"torch": torch.__version__, "sklearn": sklearn.__version__, "numpy": np.__version__},
        "history_months": C.HIST_MONTHS, "future_months": C.FUT_MONTHS,
        "use_clinical": uc, "hyperparameters": best_hp, "selected_seed": seed_used,
        "best_epoch": info["best_epoch"], "n_search_trials": len(configs),
        "gmm": {"K": K, "covariance": cov, "features": G.FEATURE_NAMES},
        "clinical_columns": C.CLINICAL_COLS, "input_ranges": prep.ranges,
        "etiology_levels": prep.etio_levels, "fill_constants": prep.fill_consts,
        "rows": {k: int(len(v)) for k, v in splits.items()},
    }
    (C.ARTIFACT_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")

    traj = []
    for sp in B:
        arr, lb = masked[sp][C.EGFR_COLS].to_numpy(), assign_all[sp][0]
        for k_ in range(K):
            for j, mo in enumerate(C.MONTHS):
                v = arr[lb == k_, j]
                v = v[~np.isnan(v)]
                traj.append(dict(Tap=sp, Nhom=k_ + 1, thang=mo, n_quan_sat=len(v),
                                 egfr_tb=float(v.mean()) if len(v) else None, egfr_sd=float(v.std()) if len(v) else None))
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

    fig, ax = plt.subplots(figsize=(8, 4))
    for k_, g in sel[sel.eligible].groupby("covariance"):
        ax.plot(g.K, g.train_BIC, marker="o", label=k_)
    ax.axvline(K, ls="--", c="gray"); ax.set(title="BIC trên Train theo số thành phần K", xlabel="K", ylabel="BIC"); ax.legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "04_gmm_bic.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    allm = np.array(C.MONTHS)
    lab = assign_all["train"][0]
    tr_all = masked["train"][C.EGFR_COLS].to_numpy()
    for k_ in range(K):
        mean = np.nanmean(tr_all[lab == k_], 0)
        ax.plot(allm, mean, marker="o", label=f"Nhóm {k_+1} (n={int((lab==k_).sum())})")
    ax.axvline(12.5, ls=":", c="k"); ax.text(13, ax.get_ylim()[1] * .97, "← lịch sử | tương lai (chỉ để mô tả) →", fontsize=8, va="top")
    ax.set(title="eGFR trung bình theo nhóm GMM (Train, chỉ tính mốc đã quan sát)", xlabel="Tháng", ylabel="eGFR"); ax.legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "05_gmm_cluster_trajectories.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    z = scaler.transform(X["train"])
    sc = ax.scatter(X["train"][:, 0], X["train"][:, 2], c=lab, cmap="tab10", s=12, alpha=.7)
    ax.set(title="Phân nhóm GMM (Train)", xlabel=G.FEATURE_NAMES[0], ylabel="Độ dốc (mL/ph/1.73m²/năm)")
    fig.tight_layout(); fig.savefig(C.FIG_DIR / "06_gmm_scatter.png"); plt.close(fig)

    log.info("XONG sau %.1f phút", (time.time() - t0) / 60)


if __name__ == "__main__":
    main()
