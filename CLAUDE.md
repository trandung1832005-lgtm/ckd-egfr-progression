# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

University ML project: predict CKD progression from eGFR over time on the CKD-ROUTE dataset. Two-stage pipeline in the layout of the reference system: **GRU** (PyTorch) forecasts eGFR at 18/24/30/36M from history at 0/6/12M; **GMM** (scikit-learn, K=3) then groups patients into Cải thiện / Ổn định / Chuyển biến xấu from the slope of the observed + GRU-predicted trajectory. CKD stage 1–5 and the treatment/diet guidance come from a rule on the **predicted 36M eGFR** (`ckd_core/guidance.py`, translated from the reference webapp). Research/demo only, not a diagnostic tool. UI text and docs are in Vietnamese. `README.md` has the full experimental design, results, permission matrix and deployment steps.

On top of the model there is a **multi-user web system** (patient / doctor / admin) in `server/` (FastAPI + SQLAlchemy/Alembic) and `frontend/` (Next.js 16, TypeScript). **The prediction system (`ckd_core/`, `artifacts/`, `scripts/`, `reports/`) must not be changed by work on the web system**; `server/` only calls `Engine.predict()`. `backend/` and `web/` are the superseded anonymous demo (kept, not deployed).

`CKD-Stage-Prediction-and-Treatment-AI-main/` is an untouched third-party reference repo (Streamlit + boosted trees, 122 MB). It is gitignored and unrelated to the models; don't modify or import from it.

## Commands

The venv must live at an ASCII path. numpy/scikit-learn fail to load DLLs from this accented project path, so a `.venv` inside the project does not work.

```bash
PY=/c/Users/Administrator/.venvs/ckd_demo/Scripts/python.exe
$PY scripts/audit_data.py                      # writes reports/data_audit.json
$PY scripts/train_all.py                       # full train+eval, ~2–4 min CPU; --trials 6 --seeds 2 for a quick run
$PY -m pytest -q tests                         # needs artifacts/ and data/*.csv (~2 min; test_server.py alone is enough for web work)
$PY -m pytest -q tests/test_server.py -k lockout   # single test

# multi-user system (dev DB is SQLite var/app.db; relative sqlite URLs only, a POSIX /c/... path breaks on Windows)
$PY -m alembic upgrade head                    # create/upgrade schema
ADMIN_PASSWORD=... $PY -m server.manage create-admin --email a@b.vn --name "Ten" --password-env ADMIN_PASSWORD
$PY -m uvicorn server.main:app --port 8000     # API, docs at /api/docs
$PY -m alembic revision --autogenerate -m "msg"   # after editing server/models.py
cd frontend && npm run dev                     # http://localhost:3000, proxies /api/* to BACKEND_URL (default 127.0.0.1:8000)
cd frontend && npx tsc --noEmit && npm run lint && npm run build

# legacy anonymous demo (superseded): $PY -m uvicorn backend.app:app --port 8000
$PY -m pytest -q tests -k test_predict_ok      # single test
```

On Windows set `PYTHONIOENCODING=utf-8` when printing Vietnamese. No linter is configured. `data/*.csv` is gitignored; the three fixed splits (`train_data.csv`, `val_data.csv`, `test_data.csv`) must never be re-split, merged, or altered.

`train_all.py` **overwrites** `artifacts/` and `reports/`. It is deterministic on CPU, so rerunning reproduces `regression_metrics.csv` byte for byte.

## Architecture

Training and inference share `ckd_core/`; `backend/app.py` is a thin FastAPI layer over `ckd_core.inference.Engine`; `web/index.html` is a static single page (vanilla JS + vendored Plotly, sections mirror the reference Streamlit app) that calls the API; the PDF report is the browser print dialog with a print stylesheet, and prediction history lives only in browser memory.

- `ckd_core/data.py`: `Preprocessor` is fit on **Train only** and pickled to `artifacts/preprocessor.joblib`. The CSVs have no NaNs, but each eGFR column (except 0M) has a repeated constant that is a median fill. `detect_fill_constants` finds these on Train, and `mask_fill` turns them into NaN, meaning unobserved. Everything downstream relies on masks: loss, metrics, and GRU inputs `[scaled eGFR forward-filled, observed flag, Δt/12]`. `transform(apply_fill=True)` is for the CSVs; inference uses `apply_fill=False` because user-entered NaN is already NaN.
- `ckd_core/gru.py`: the GRU outputs a **residual added to the last observed eGFR**. Loss is masked SmoothL1. `use_clinical` is itself a searched hyperparameter. Random search (30 configs) and checkpoint choice use Validation MAE only; Test is computed after selection.
- `ckd_core/gmm.py`: the only GMM feature is the OLS slope of [observed history + 4 GRU-predicted points]; it never sees real future eGFR. It is winsorized at Train p5–p95 (`ClippedScaler`) because a few noisy outliers otherwise get their own cluster. Single-observation patients get no assumed slope, because assuming 0 once created an artificial cluster. K is fixed at 3; only the covariance type is chosen by Validation log-likelihood. Cluster names are assigned by **rank** of mean Train slope, so they are relative: "Ổn định" still declines ~2/yr and "Cải thiện" is roughly flat. Real future eGFR and `CKD progression` are used only to describe clusters afterwards.
- `ckd_core/guidance.py`: rule `eGFR -> Giai đoạn 1..5` and the Vietnamese guidance text. Pure rules, no learning.
- `ckd_core/inference.py`: `Engine` loads `artifacts/*` plus `reports/gmm_cluster_profile.csv`. If loading fails it sets `ready=False` and the API returns 503, so there are no fake predictions. `InputError` maps to HTTP 422 with user-safe messages, and the global handler hides internals.
- `reports/*.csv|json` are read by `/api/results` for the UI. `tests/test_api.py::test_pipeline_consistency_with_batch_eval` asserts the API output equals the evaluation-time prediction; keep that invariant when touching preprocessing.

## Constraints to keep

- Pickles are version-sensitive: `requirements*.txt` pin torch/sklearn/numpy to the versions recorded in `artifacts/meta.json`. Retraining with other versions requires updating both.
- Deployment: `web/` goes to Vercel (Root Directory `web`, backend URL in `web/config.js`). The backend goes to Render or HF via `Dockerfile` (`requirements-api.txt`, set `ALLOWED_ORIGINS`). Vercel cannot host the PyTorch backend or Streamlit.
- Don't commit patient-level data: `data/*.csv`, `data/processed/` and `reports/predictions_*.csv` are gitignored on purpose.
- Report results honestly: GRU only marginally beats the Linear Regression baseline (mean Test MAE over 5 seeds 3.70 vs 3.76), and the GMM labels are relative (see above). README states this.

## Multi-user system (`server/`, `frontend/`)

- **Authorization lives in `server/deps.py`** (`patient_access`, `require_roles`), never only in the UI. Patient: own data only. Doctor: only patients with an active `doctor_patient_assignments` row, and the doctor must be `approved`. Admin: no health data (403). Out-of-scope access returns **404** for patient/doctor so existence is not leaked. Prediction access is decided from the stored `Prediction.patient_id`, not an ID the client supplies. Any new endpoint touching a patient must call `patient_access` and get a test in `tests/test_server.py`.
- **Sessions are server-side** (`sessions` table, cookie holds a random token, only its HMAC is stored), so lock/unassign/logout/password change revoke immediately. CSRF = `Origin`/`Referer` allow-list check in `check_csrf` + SameSite=Lax. The browser only calls same-origin `/api/*`; `frontend/next.config.ts` rewrites it to the backend, which is why `ALLOWED_ORIGINS` must contain the frontend origin.
- **Data is versioned, not edited**: an eGFR correction creates a new `egfr_records` row (`replaces_id`) and voids the old; `prediction_inputs` are immutable and each `predictions` row stores the model version. Don't add UPDATE paths that overwrite health data. Audit details must never contain passwords, tokens, eGFR or clinical values (`audit.py` filters keys).
- No default accounts or seeded patients (the dataset is research data, not app data). First admin only via `server.manage create-admin`. Doctors/admins are created by an admin and activate through a one-time token link; without SMTP the link is shown to the admin once.
- `TRUSTED_PROXY_HOPS` controls how much of `X-Forwarded-For` is trusted for IP rate limits (default 0). Don't re-enable uvicorn `--proxy-headers` with `*`; it makes the IP spoofable. The rate limiter is in-process memory.
- Tests use a temp SQLite DB built by the real Alembic migration (`tests/conftest.py` sets env before importing `server`). PostgreSQL has not been tested locally (none installed).
- Frontend pitfalls: Alembic reads `alembic.ini` with the Windows codepage, so keep it ASCII; `email-validator` rejects reserved TLDs such as `.test`, so use e.g. `@e2e-mail.vn` for test accounts; `create-next-app` generated `frontend/AGENTS.md` (Next 16 differs from older versions; docs are in `frontend/node_modules/next/dist/docs/`). `cacheComponents` is off because all pages are client-rendered behind login.
- When killing dev servers on Windows, stop by listening port (`Get-NetTCPConnection -LocalPort 8000 | Stop-Process`), not by command-line pattern, which can kill your own shell.
