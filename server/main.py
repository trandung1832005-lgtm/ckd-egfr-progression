"""Ứng dụng FastAPI đa người dùng.  uvicorn server.main:app --port 8000"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .routers import admin, auth, doctor, patients, system

log = logging.getLogger("ckd-server")

app = FastAPI(title="CKD eGFR – hệ thống đa người dùng",
              docs_url=None if config.IS_PROD else "/api/docs",
              redoc_url=None, openapi_url=None if config.IS_PROD else "/api/openapi.json")

app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"        # dữ liệu sức khỏe không được cache
    return resp


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("Lỗi không lường trước")                 # chi tiết chỉ ghi log máy chủ
    return JSONResponse({"detail": "Lỗi nội bộ máy chủ. Vui lòng thử lại sau."}, status_code=500)


for r in (system.router, auth.router, patients.router, doctor.router, admin.router):
    app.include_router(r)
