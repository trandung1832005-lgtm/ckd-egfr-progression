"""Cấu hình trung tâm. Mọi đường dẫn tính tương đối từ thư mục gốc repo."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACT_DIR = ROOT / "artifacts"
REPORT_DIR = ROOT / "reports"
FIG_DIR = REPORT_DIR / "figures"

SPLIT_FILES = {
    "train": DATA_DIR / "train_data.csv",
    "val": DATA_DIR / "val_data.csv",
    "test": DATA_DIR / "test_data.csv",
}

SEED = 42

# --- cột dữ liệu (đúng tên trong file CSV) ---
EGFR_COLS = ["eGFR(0M)", "eGFR(6M)", "eGFR(12M)", "eGFR(18M)", "eGFR(24M)", "eGFR(30M)", "eGFR(36M)"]
MONTHS = [0, 6, 12, 18, 24, 30, 36]
N_HIST = 3                      # lịch sử: 0M, 6M, 12M
HIST_COLS = EGFR_COLS[:N_HIST]
FUT_COLS = EGFR_COLS[N_HIST:]   # đích: 18M, 24M, 30M, 36M
HIST_MONTHS = MONTHS[:N_HIST]
FUT_MONTHS = MONTHS[N_HIST:]

CLIN_NUM = ["age", "SBP", "BMI", "Hb", "Alb", "Cr", "UPCR", "CKD_stage"]
CLIN_LOG = ["Cr", "UPCR"]       # lệch phải -> log1p trước khi chuẩn hóa
CLIN_BIN = ["gender", "hypertension", "prevalence of CVD", "diabetes",
            "use of RAASi", "use of CCB", "use of diuretics", "proteinuria"]
CLIN_CAT = ["etiology of CKD"]
CLINICAL_COLS = CLIN_NUM + CLIN_BIN + CLIN_CAT
LABEL_COL = "CKD progression"   # kết cục tương lai: KHÔNG dùng làm đầu vào

# Một giá trị eGFR lặp >= ngưỡng này trong Train được coi là hằng số điền thiếu
FILL_MIN_COUNT = 5
