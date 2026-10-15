from __future__ import annotations

import json

from fastapi import Request
from sqlalchemy.orm import Session

from . import config

from .models import AuditLog, User

_FORBIDDEN = {"password", "token", "secret", "clinical", "egfr"}   # không bao giờ ghi các khóa này vào log


def client_ip(request: Request | None) -> str | None:
    """IP của khách. Chỉ tin X-Forwarded-For theo đúng số lớp proxy cấu hình (TRUSTED_PROXY_HOPS), tránh bị giả IP."""
    if request is None or request.client is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if config.TRUSTED_PROXY_HOPS > 0 and fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[max(0, len(parts) - config.TRUSTED_PROXY_HOPS)][:64]
    return request.client.host[:64]


def log(db: Session, request: Request | None, action: str, actor: User | None = None, *,
        target_type: str | None = None, target_id: str | None = None, detail: dict | None = None,
        actor_id: str | None = None, commit: bool = True) -> None:
    safe = {k: v for k, v in (detail or {}).items() if not any(f in k.lower() for f in _FORBIDDEN)}
    db.add(AuditLog(
        actor_id=actor.id if actor else actor_id, actor_role=actor.role if actor else None, action=action,
        target_type=target_type, target_id=target_id, ip=client_ip(request),
        detail=json.dumps(safe, ensure_ascii=False, default=str) if safe else None))
    if commit:
        db.commit()
