# Backend đa người dùng (FastAPI + PyTorch CPU + SQLAlchemy). Dùng được trên Render / Hugging Face Spaces (Docker).
FROM python:3.12-slim
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY ckd_core ckd_core
COPY server server
COPY migrations migrations
COPY alembic.ini .
COPY artifacts artifacts
COPY reports/*.csv reports/*.json reports/
ENV PORT=8000 APP_ENV=prod PYTHONUNBUFFERED=1
# Áp dụng migration rồi chạy API. Giao diện nằm trên Vercel. Admin đầu tiên tạo bằng: python -m server.manage create-admin
CMD ["sh", "-c", "alembic upgrade head && uvicorn server.main:app --host 0.0.0.0 --port ${PORT}"]
