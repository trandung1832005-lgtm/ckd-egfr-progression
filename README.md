# Dự đoán tiến triển bệnh thận mạn tính qua eGFR theo thời gian (GRU + GMM)

Demo nghiên cứu: **GRU** dự đoán eGFR tại 18/24/30/36 tháng từ lịch sử 0/6/12 tháng; **GMM** phân nhóm kiểu quỹ đạo eGFR từ lịch sử. Dữ liệu CKD-ROUTE (Train/Validation/Test cố định).
Hệ thống chỉ phục vụ nghiên cứu và minh họa, **không** phải công cụ chẩn đoán.

```
ckd_core/     lõi: tiền xử lý, GRU (PyTorch), GMM, baseline, chỉ số, suy luận
scripts/      audit_data.py, train_all.py (huấn luyện + đánh giá + xuất artifact/biểu đồ)
backend/      FastAPI: /api/health, /api/meta, /api/results, /api/predict, /api/predict-csv
web/          giao diện (HTML/JS + Plotly), triển khai lên Vercel (thư mục gốc = web)
artifacts/    mô hình GRU, preprocessor (scaler…), GMM, meta.json  (nhỏ, ~200 KB, có trong repo)
reports/      bảng chỉ số, biểu đồ, báo cáo kiểm định dữ liệu
tests/        pytest cho API với mô hình thật
data/         đặt 3 file CSV ở đây (KHÔNG commit)
```

## Thiết kế thực nghiệm (rút ra từ dữ liệu thực tế)

- Dữ liệu: Train 796 / Val 171 / Test 171 dòng, 25 cột. Giữ nguyên ba tập, không chia lại, không gộp.
- **Đầu vào GRU**: eGFR 0M/6M/12M + các biến lâm sàng ban đầu (tuổi, huyết áp, BMI, Hb, Alb, Cr, UPCR, CKD_stage, giới, tăng huyết áp, bệnh tim mạch, đái tháo đường, RAASi, CCB, lợi tiểu, protein niệu, nguyên nhân CKD). Việc có dùng biến lâm sàng hay không được **chọn bằng Validation** trong tìm siêu tham số.
- **Đầu ra**: eGFR 18M, 24M, 30M, 36M (dữ liệu có đủ 4 mốc này).
- **`CKD progression` không được dùng làm đầu vào** (là kết cục tương lai, sẽ rò rỉ). Chỉ dùng để mô tả nhóm GMM sau khi đã phân nhóm.
- **Dữ liệu thiếu**: file CSV không có ô trống, nhưng mỗi cột eGFR (trừ 0M) có một giá trị lặp rất nhiều lần (6M: 18%, 36M: 53% dòng Train) – dấu hiệu điền thiếu bằng trung vị. Pipeline phát hiện các hằng số này **trên Train**, coi là *chưa quan sát*, không tính vào loss/chỉ số, và đưa vào GRU dưới dạng cờ “có đo” + thời gian từ lần đo cuối. Đây là suy luận từ dữ liệu (chi tiết ở `reports/data_audit.json`); nếu bạn có thông tin khác về cách điền, cần xem lại bước này.
- Mọi tham số tiền xử lý (chuẩn hóa, hằng số điền, mã hóa nguyên nhân CKD) **chỉ fit trên Train**, lưu trong `artifacts/preprocessor.joblib` và dùng lại khi suy luận.
- **Chọn mô hình chỉ bằng Validation**: tìm ngẫu nhiên 30 cấu hình GRU, early stopping, chọn checkpoint và seed theo MAE Validation; chọn (K, covariance) của GMM theo log-likelihood Validation. Test chỉ tính một lần sau khi mô hình đã cố định.
- Không có `patient_id` trong dữ liệu → **không kiểm tra được trùng bệnh nhân giữa các tập**; chỉ xác nhận không có dòng trùng nguyên văn giữa các tập. Nếu một bệnh nhân có thể nằm ở nhiều tập, kết quả Test có thể lạc quan.

## Kết quả (đã chạy thật; xem `reports/`)

MAE trên eGFR (mL/phút/1,73 m²), chỉ tính các mốc đã đo:

| Mô hình | Validation (N=388) | Test (N=329) |
|---|---|---|
| Giữ eGFR gần nhất | 4,84 | 4,29 |
| Linear Regression (lịch sử) | 4,62 | 3,76 |
| **GRU** (seed chọn theo Val) | **4,60** | **3,54** |

Cần đọc kỹ:
- GRU tốt hơn rõ rệt so với “giữ eGFR gần nhất”, nhưng **chỉ hơn Linear Regression rất ít**. Qua 5 seed cùng cấu hình, MAE Test trung bình = **3,70 ± 0,08**, nghĩa là so với Linear Regression (3,76) chênh lệch nằm trong mức dao động giữa các seed. Con số 3,54 là seed được chọn theo Validation, không phải kết quả điển hình.
- Mốc xa (30M, 36M) sai số lớn hơn và có ít mẫu hơn; tỷ lệ chưa quan sát ở 36M là ~53–63%, nên chỉ số dựa trên nhóm còn được theo dõi.
- **GMM** (K=3, covariance full): nhóm khá mất cân bằng (~80% bệnh nhân ở một nhóm) và **độ ổn định khi khởi tạo lại thấp** (ARI trung bình 0,53, thấp nhất 0,22). Hai nhóm nhỏ chỉ có ít bệnh nhân còn dữ liệu theo dõi tương lai (nhóm 2: Train n=6, Val và Test n=0). Nhóm GMM chỉ mô tả kiểu quỹ đạo thống kê trên mẫu này, **không** đồng nghĩa giai đoạn CKD hay chẩn đoán, và không phải mô hình dự báo eGFR. AIC/BIC/log-likelihood chỉ dùng để so sánh cấu hình GMM với nhau, không so với MAE của GRU.
- Pipeline tái lập: chạy lại `train_all.py` cho ra `regression_metrics.csv` giống hệt (seed cố định, CPU).

## Chạy cục bộ

Windows: nếu thư mục dự án có dấu tiếng Việt, hãy tạo venv ở **đường dẫn không dấu** (numpy/scikit-learn không nạp được DLL từ đường dẫn có dấu).

```powershell
py -3.12 -m venv C:\venvs\ckd_demo
C:\venvs\ckd_demo\Scripts\python -m pip install -r requirements.txt

# 1) đặt train_data.csv, val_data.csv, test_data.csv vào data/
# 2) kiểm định dữ liệu
C:\venvs\ckd_demo\Scripts\python scripts\audit_data.py
# 3) huấn luyện + đánh giá (~2–4 phút trên CPU; --trials 6 để chạy nhanh)
C:\venvs\ckd_demo\Scripts\python scripts\train_all.py
# 4) chạy demo (API + giao diện cùng một địa chỉ)
C:\venvs\ckd_demo\Scripts\python -m uvicorn backend.app:app --port 8000   # mở http://localhost:8000
# 5) kiểm thử
C:\venvs\ckd_demo\Scripts\python -m pytest -q tests
```

Chạy lại `train_all.py` sẽ **ghi đè** `artifacts/` và `reports/`; sao lưu trước nếu cần giữ bản cũ. Suy luận không bao giờ huấn luyện lại; thiếu artifact thì `/api/health` báo `model_not_ready` và giao diện vô hiệu hóa nút dự đoán.

## Triển khai: GitHub → Vercel (frontend) + Render (backend)

Vercel không chạy được PyTorch/scikit-learn ổn định (giới hạn dung lượng function) và không chạy Streamlit của repo tham khảo, nên kiến trúc là:

```
Trình duyệt ──> Vercel (thư mục web/, tĩnh) ──fetch──> Render (Docker, FastAPI + artifacts/)
```

1. **Đẩy lên GitHub** (repo mới, không có `data/*.csv` nhờ `.gitignore`):
   ```
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
   ```
2. **Backend (Render)**: New → Blueprint (đọc `render.yaml`) hoặc New → Web Service → chọn repo, Runtime = Docker. Đặt biến môi trường `ALLOWED_ORIGINS` = URL Vercel (làm sau bước 3). Kiểm tra `https://<backend>/api/health` trả `model_ready: true`. (Gói free có thể “ngủ” và khởi động chậm lần đầu.) Có thể dùng Hugging Face Spaces (Docker) với cùng Dockerfile, cổng 7860: đặt `PORT=7860`.
3. **Frontend (Vercel)**: Add New Project → import repo → **Root Directory = `web`**, Framework Preset = Other, không có build command. Trước đó sửa `web/config.js`: `window.CKD_API_URL = "https://<backend>.onrender.com";` rồi commit/push.
4. Quay lại Render, đặt `ALLOWED_ORIGINS` = URL Vercel và redeploy backend.
5. Kiểm tra: mở URL Vercel → thanh trạng thái xanh “Mô hình GRU và GMM đã sẵn sàng” → nhập dữ liệu → dự đoán.

Checkpoint, scaler và GMM nằm trong `artifacts/` (khoảng 200 KB) nên commit thẳng vào repo; Docker image đọc từ đó. Nếu sau này mô hình lớn hơn, hãy chuyển sang GitHub Releases/Hugging Face Hub và thêm bước tải khi khởi động.

## Giới hạn

- Dữ liệu nhỏ, nhiều mốc chưa quan sát, không có mã bệnh nhân.
- Mã của giới tính và nguyên nhân CKD giữ nguyên như file dữ liệu; hệ thống không diễn giải ý nghĩa y khoa của các mã đó.
- Nhập giá trị ngoài khoảng dữ liệu huấn luyện sẽ có cảnh báo; kết quả khi đó kém tin cậy.
- Chưa có kiểm chứng ngoài (dữ liệu độc lập, bệnh viện khác).
