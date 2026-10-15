# Backend suy luận (FastAPI + PyTorch CPU). Dùng được trên Render / Hugging Face Spaces (Docker).
FROM python:3.12-slim
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY ckd_core ckd_core
COPY backend backend
COPY artifacts artifacts
COPY reports/*.csv reports/*.json reports/
# Chỉ phục vụ API; giao diện nằm trên Vercel
ENV PORT=8000
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
