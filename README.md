# Hệ thống web theo dõi và dự đoán tiến triển bệnh thận mạn (đa người dùng)

Hệ thống cho **bệnh nhân**, **bác sĩ** và **quản trị viên**: theo dõi eGFR theo thời gian, dự đoán eGFR 18/24/30/36 tháng bằng **GRU**, phân nhóm xu hướng bằng **GMM**, kèm hướng dẫn chăm sóc theo mức eGFR dự đoán. Có đăng nhập, phân quyền theo vai trò + quyền sở hữu dữ liệu, lưu trữ trong cơ sở dữ liệu và nhật ký truy cập.

> Chỉ phục vụ nghiên cứu và minh họa. Không phải công cụ chẩn đoán; kết quả mô hình chưa được kiểm chứng lâm sàng.
> Hệ thống **khởi đầu trống**: không có tài khoản hay bệnh nhân mẫu. Dữ liệu huấn luyện (CKD-ROUTE) chỉ dùng để huấn luyện mô hình, không nạp vào ứng dụng.

## Kiến trúc

```
Trình duyệt ──> Next.js (frontend/, Vercel) ──/api/* (rewrite, cùng domain)──> FastAPI (server/, Render, Docker)
                                                                               ├─ PostgreSQL (prod) / SQLite (dev)
                                                                               └─ ckd_core + artifacts/ : GRU + GMM (PyTorch CPU)
```

| Thư mục | Nội dung |
|---|---|
| `frontend/` | Next.js (TypeScript), giao diện riêng cho 3 vai trò, responsive |
| `server/` | FastAPI: xác thực, RBAC, API, kiểm toán; `manage.py` tạo admin đầu tiên |
| `migrations/` | Alembic: lược đồ cơ sở dữ liệu |
| `ckd_core/`, `artifacts/`, `scripts/`, `reports/` | **Hệ thống dự đoán GRU/GMM (không thay đổi)**; `server/` chỉ gọi `Engine.predict()` |
| `tests/` | `test_server.py` (xác thực, phân quyền, dữ liệu, mô hình), `test_api.py` (API ẩn danh cũ) |
| `backend/`, `web/` | Bản demo ẩn danh trước đây, đã được thay thế; không dùng khi triển khai |

Cookie phiên là `HttpOnly`, `SameSite=Lax`, `Secure` ở production. Frontend chỉ gọi cùng domain `/api/*` rồi Next chuyển tiếp sang backend, nên cookie là cookie cùng domain.

## Ma trận quyền

| Hành động | Bệnh nhân | Bác sĩ | Admin |
|---|---|---|---|
| Tự đăng ký | ✅ (chỉ vai trò bệnh nhân) | ❌ (admin tạo) | ❌ (tạo bằng lệnh phía máy chủ) |
| Hồ sơ cá nhân, đổi mật khẩu | ✅ | ✅ | ✅ |
| Nhập/sửa eGFR | chính mình | bệnh nhân được phân công | ❌ |
| Xem hồ sơ, biểu đồ, lịch sử | chính mình | bệnh nhân được phân công (có ghi nhật ký) | ❌ (403) |
| Chạy dự đoán | cho chính mình | bệnh nhân được phân công | ❌ |
| Nhận xét chuyên môn, kế hoạch | ❌ (không xem được) | ✅ | ❌ |
| Tạo/khóa tài khoản, phê duyệt bác sĩ, phân công | ❌ | ❌ | ✅ |
| Nhật ký hoạt động, tình trạng hệ thống | ❌ | ❌ | ✅ |

Quy tắc đặt ở backend (`server/deps.py`), không dựa vào việc ẩn nút. Ngoài phạm vi, bác sĩ/bệnh nhân nhận **404** (không lộ hồ sơ có tồn tại), admin nhận 403. Quyền với một kết quả dự đoán được xác định theo chủ sở hữu thật của bản ghi, không theo ID client gửi. Thu hồi phân công/phê duyệt và khóa tài khoản có hiệu lực ngay (phiên bị thu hồi phía máy chủ).

## Cơ sở dữ liệu

`users`, `patient_profiles`, `doctor_profiles` (có `approved`), `doctor_patient_assignments` (chỉ mục duy nhất cho phân công đang hiệu lực), `egfr_records` (sửa = tạo bản mới thay thế, giữ bản cũ), `prediction_inputs` (phiên bản đầu vào bất biến), `predictions` (kèm phiên bản mô hình), `clinical_notes`, `audit_logs`, `sessions`, `password_tokens`. ID là UUID. Khóa ngoại và ràng buộc được kiểm thử (kể cả SQLite bật `foreign_keys`).

## API chính (`/api/docs` khi `APP_ENV=dev`)

`POST /auth/register|login|logout|change-password|forgot-password|reset-password` · `GET /auth/me` · `PUT /me/profile` ·
`GET /patients/{id}` · `GET|POST /patients/{id}/egfr` · `POST /patients/{id}/egfr/{rid}/replace` · `GET /patients/{id}/inputs/suggest` ·
`POST|GET /patients/{id}/predictions` · `GET /predictions/{id}` · `GET /patients/{id}/history` · `GET|POST /patients/{id}/notes` ·
`GET /doctor/patients` · `GET /admin/overview|users|assignments|audit-logs|system` · `POST /admin/users` · `PATCH /admin/users/{id}` ·
`POST|DELETE /admin/assignments` · `GET /models/status|spec` · `GET /health`

## Bảo mật đã triển khai (và giới hạn)

- Mật khẩu băm **Argon2id**; chính sách ≥10 ký tự gồm chữ và số. Không có tài khoản mặc định: admin đầu tiên chỉ tạo bằng `python -m server.manage create-admin` (hỏi mật khẩu, không hiển thị). Bác sĩ/admin do admin tạo kèm liên kết kích hoạt dùng một lần, hiệu lực 72 giờ.
- Phiên phía máy chủ (thu hồi được, hết hạn 12 giờ); đăng xuất, đổi/đặt lại mật khẩu và khóa tài khoản đều thu hồi phiên.
- Khóa tạm 15 phút sau 5 lần đăng nhập sai; giới hạn tần suất đăng nhập, đăng ký, quên mật khẩu, dự đoán. Phản hồi đăng nhập/quên mật khẩu không cho biết email có tồn tại.
- Chống CSRF: kiểm tra `Origin`/`Referer` với danh sách cho phép + `SameSite=Lax`. CORS chỉ cho origin cấu hình. Header bảo mật, `Cache-Control: no-store` cho `/api`.
- Nhật ký kiểm toán cho đăng nhập, khóa/mở, phân quyền, mở hồ sơ, tạo dự đoán; **không** ghi mật khẩu, token hay số liệu y tế.
- Bộ giới hạn tần suất lưu trong bộ nhớ (đủ cho 1 instance; nhiều instance cần Redis). `TRUSTED_PROXY_HOPS` quyết định tin `X-Forwarded-For` bao nhiêu lớp (mặc định 0; Vercel→Render là 2).
- Dữ liệu sức khỏe lưu trong CSDL **không mã hóa ở mức trường**; dựa vào mã hóa của nhà cung cấp CSDL. Chưa có xác minh email khi đăng ký, chưa có 2FA, chưa có chính sách sao lưu/tự xóa dữ liệu: cần bổ sung nếu dùng thực tế.

## Chạy cục bộ

Windows: tạo venv ở **đường dẫn không dấu** (numpy/scikit-learn không nạp được DLL từ đường dẫn có dấu tiếng Việt).

```powershell
py -3.12 -m venv C:\venvs\ckd_demo
C:\venvs\ckd_demo\Scripts\python -m pip install -r requirements.txt

# (một lần) cơ sở dữ liệu SQLite cục bộ var/app.db + quản trị viên đầu tiên
C:\venvs\ckd_demo\Scripts\python -m alembic upgrade head
C:\venvs\ckd_demo\Scripts\python -m server.manage create-admin --email ban@mail.com --name "Tên của bạn"

# backend (http://localhost:8000, tài liệu API: /api/docs)
C:\venvs\ckd_demo\Scripts\python -m uvicorn server.main:app --port 8000

# frontend (http://localhost:3000)
cd frontend; npm install; npm run dev
```

Cần đã có `artifacts/` (có sẵn trong repo). Nếu chưa, chạy `scripts/train_all.py` (xem phần mô hình). Thiếu artifact thì giao diện báo "mô hình chưa sẵn sàng", không tạo kết quả giả. Biến môi trường: xem `.env.example` và `frontend/.env.example`. Email đăng ký/đăng nhập phải có tên miền hợp lệ (tên miền dành riêng như `.test` bị từ chối).

Email (quên mật khẩu/kích hoạt): đặt `SMTP_*`. Khi chưa cấu hình, hệ thống vẫn hoạt động: admin nhận liên kết kích hoạt/đặt lại để tự chuyển cho người dùng; luồng "Quên mật khẩu" tự phục vụ chỉ gửi được khi có SMTP.

## Kiểm thử

```powershell
C:\venvs\ckd_demo\Scripts\python -m pytest -q tests          # xác thực, phân quyền, ràng buộc DB, mô hình thật
cd frontend; npx tsc --noEmit; npm run lint; npm run build       # kiểm tra kiểu, lint, build
```

Đã chạy thêm kiểm thử trình duyệt end-to-end (Playwright/Edge) với DB tạm: đăng ký, nhập và sửa eGFR, dự đoán, bác sĩ, quản trị viên, truy cập chéo giữa các bệnh nhân, khóa tài khoản, màn hình 390px. Chưa kiểm thử trên PostgreSQL thật (máy phát triển không có PostgreSQL); migration chỉ dùng kiểu cột chuẩn, cần chạy `alembic upgrade head` trên Postgres lần đầu triển khai và kiểm tra.

## Triển khai: GitHub → Vercel (frontend) + Render (backend) + PostgreSQL

Chưa triển khai; các bước bạn cần làm (tôi không có quyền truy cập tài khoản của bạn):

1. **GitHub**: tạo repo, `git push`. `.gitignore` đã loại `data/*.csv`, `.env`, `var/`, `node_modules`.
2. **PostgreSQL**: tạo CSDL miễn phí (Neon/Supabase/Render Postgres), lấy chuỗi `postgresql://user:pass@host/db` (bật SSL nếu nhà cung cấp yêu cầu, ví dụ thêm `?sslmode=require`).
3. **Backend (Render)**: New → Blueprint (đọc `render.yaml`) hoặc Web Service → Docker. Đặt `DATABASE_URL`, `FRONTEND_URL` (URL Vercel), `ALLOWED_ORIGINS` (cùng URL), tùy chọn `SMTP_*`; `SECRET_KEY` Render tự sinh. Container tự chạy `alembic upgrade head` khi khởi động. Tạo admin đầu tiên **từ máy bạn** nhắm vào CSDL production (gói Render miễn phí không có Shell): đặt `DATABASE_URL` là chuỗi kết nối **trực tiếp** (không qua pgbouncer) rồi chạy `python -m server.manage create-admin --email ... --name ...` (bảng đã được container tạo khi khởi động). Kiểm tra `https://<backend>/api/health`.
4. **Frontend (Vercel)**: Import repo, **Root Directory = `frontend`**, Framework = Next.js, biến môi trường `BACKEND_URL=https://<backend>.onrender.com`. Sau khi có URL Vercel, quay lại Render đặt `FRONTEND_URL` và `ALLOWED_ORIGINS`, redeploy.
5. **Kiểm tra bản thật**: đăng ký bệnh nhân, đăng nhập admin, tạo bác sĩ, phân công, dự đoán, kiểm tra phân quyền chéo; xác nhận cookie có cờ `Secure` và `HttpOnly`, và giới hạn tần suất nhận đúng IP khách (`TRUSTED_PROXY_HOPS=2`).

Gói Render miễn phí "ngủ" khi không dùng nên yêu cầu đầu tiên chậm.

## Phần mô hình AI (GRU + GMM, không thay đổi)

### Thiết kế thực nghiệm (rút ra từ dữ liệu thực tế)

- Dữ liệu: Train 796 / Val 171 / Test 171 dòng, 25 cột. Giữ nguyên ba tập, không chia lại, không gộp.
- **Đầu vào GRU**: eGFR 0M/6M/12M + các biến lâm sàng ban đầu (tuổi, huyết áp, BMI, Hb, Alb, Cr, UPCR, CKD_stage, giới, tăng huyết áp, bệnh tim mạch, đái tháo đường, RAASi, CCB, lợi tiểu, protein niệu, nguyên nhân CKD). Việc có dùng biến lâm sàng hay không được **chọn bằng Validation** trong tìm siêu tham số.
- **Đầu ra**: eGFR 18M, 24M, 30M, 36M (dữ liệu có đủ 4 mốc này).
- **`CKD progression` không được dùng làm đầu vào** (là kết cục tương lai, sẽ rò rỉ). Chỉ dùng để mô tả nhóm GMM sau khi đã phân nhóm.
- **Dữ liệu thiếu**: file CSV không có ô trống, nhưng mỗi cột eGFR (trừ 0M) có một giá trị lặp rất nhiều lần (6M: 18%, 36M: 53% dòng Train) – dấu hiệu điền thiếu bằng trung vị. Pipeline phát hiện các hằng số này **trên Train**, coi là *chưa quan sát*, không tính vào loss/chỉ số, và đưa vào GRU dưới dạng cờ “có đo” + thời gian từ lần đo cuối. Đây là suy luận từ dữ liệu (chi tiết ở `reports/data_audit.json`); nếu bạn có thông tin khác về cách điền, cần xem lại bước này.
- Mọi tham số tiền xử lý (chuẩn hóa, hằng số điền, mã hóa nguyên nhân CKD) **chỉ fit trên Train**, lưu trong `artifacts/preprocessor.joblib` và dùng lại khi suy luận.
- **Chọn mô hình chỉ bằng Validation**: tìm ngẫu nhiên 30 cấu hình GRU, early stopping, chọn checkpoint và seed theo MAE Validation; loại covariance của GMM chọn theo log-likelihood Validation. Test chỉ tính một lần sau khi mô hình đã cố định.
- **GMM dùng dự đoán của GRU, không dùng eGFR tương lai thật.** Đặc trưng duy nhất là độ dốc OLS (mL/ph/1,73 m²/năm) của quỹ đạo gồm các mốc đã đo + 4 mốc GRU dự đoán; tính được cho mọi bệnh nhân kể cả khi chỉ có 1 mốc đo (bản thử đầu dùng thêm độ dốc lịch sử với giả định = 0 cho bệnh nhân 1 mốc và tạo ra một nhóm nhân tạo, nên đã bỏ). Độ dốc được cắt ở phân vị 5–95% của Train (fit trên Train) vì đuôi dài do nhiễu đo; không cắt thì GMM dành riêng một nhóm cho 5 ngoại lai. Với Train, dự đoán GRU là dự đoán trong mẫu nên mượt hơn Val/Test một chút.
- **Tên nhóm gán theo thứ hạng độ dốc trung bình trên Train** (thấp nhất = Chuyển biến xấu, giữa = Ổn định, cao nhất = Cải thiện). Đây là nhãn **tương đối**, không phải định nghĩa tuyệt đối (xem phần Kết quả).
- Không có `patient_id` trong dữ liệu → **không kiểm tra được trùng bệnh nhân giữa các tập**; chỉ xác nhận không có dòng trùng nguyên văn giữa các tập. Nếu một bệnh nhân có thể nằm ở nhiều tập, kết quả Test có thể lạc quan.

### Kết quả mô hình (đã chạy thật; xem `reports/`)

MAE trên eGFR (mL/phút/1,73 m²), chỉ tính các mốc đã đo:

| Mô hình | Validation (N=388) | Test (N=329) |
|---|---|---|
| Giữ eGFR gần nhất | 4,84 | 4,29 |
| Linear Regression (lịch sử) | 4,62 | 3,76 |
| **GRU** (seed chọn theo Val) | **4,60** | **3,54** |

Cần đọc kỹ:
- GRU tốt hơn rõ rệt so với “giữ eGFR gần nhất”, nhưng **chỉ hơn Linear Regression rất ít**. Qua 5 seed cùng cấu hình, MAE Test trung bình = **3,70 ± 0,08**, nghĩa là so với Linear Regression (3,76) chênh lệch nằm trong mức dao động giữa các seed. Con số 3,54 là seed được chọn theo Validation, không phải kết quả điển hình.
- Mốc xa (30M, 36M) sai số lớn hơn và có ít mẫu hơn; tỷ lệ chưa quan sát ở 36M là ~53–63%, nên chỉ số dựa trên nhóm còn được theo dõi.
- **GMM (K=3)**: ổn định khi khởi tạo lại (ARI trung bình 0,95, thấp nhất 0,91). Tỷ lệ nhóm Train: Chuyển biến xấu 17% (độ dốc TB −5,7/năm), Ổn định 59% (−2,0), Cải thiện 24% (+1,1). Tỷ lệ `CKD progression` (nhãn **không** dùng khi phân nhóm) tăng đơn điệu theo thứ hạng ở cả Train/Val/Test (ví dụ Test 65% / 35% / 5%), là bằng chứng độc lập ủng hộ cách xếp thứ hạng.
- **Nhưng cách đặt tên cần đọc cẩn thận:** 66% bệnh nhân có độ dốc dự đoán âm; nhóm “Ổn định” vẫn giảm ~2/năm và nhóm “Cải thiện” chỉ đi ngang hoặc nhích lên nhẹ, thực tế eGFR sau đó của họ vẫn giảm (Train −0,5, Test −4,5 mL/ph). Thay đổi eGFR thực tế khớp thứ hạng ở Train nhưng không hoàn toàn ở Val/Test (mẫu nhỏ, n=17–26). Nhóm GMM mô tả kiểu xu hướng thống kê trên mẫu này, **không** phải giai đoạn CKD hay chẩn đoán, và không phải mô hình dự báo eGFR. Do GMM nhận dự đoán của GRU, chất lượng phân nhóm phụ thuộc chất lượng GRU. AIC/BIC/log-likelihood chỉ dùng so sánh cấu hình GMM, không so với MAE của GRU.
- Pipeline tái lập: chạy lại `train_all.py` cho ra `regression_metrics.csv` giống hệt (seed cố định, CPU).

### Giới hạn của mô hình và dữ liệu

- Dữ liệu nhỏ, nhiều mốc chưa quan sát, không có mã bệnh nhân.
- Mã của giới tính và nguyên nhân CKD giữ nguyên như file dữ liệu; hệ thống không diễn giải ý nghĩa y khoa của các mã đó.
- Nhập giá trị ngoài khoảng dữ liệu huấn luyện sẽ có cảnh báo; kết quả khi đó kém tin cậy.
- Chưa có kiểm chứng ngoài (dữ liệu độc lập, bệnh viện khác).
