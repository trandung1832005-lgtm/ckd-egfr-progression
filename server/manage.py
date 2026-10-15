"""Lệnh quản trị phía máy chủ.

    python -m server.manage create-admin --email a@b.com --name "Tên"      # hỏi mật khẩu, không hiện khi gõ
    ADMIN_PASSWORD=... python -m server.manage create-admin --email ... --name ... --password-env ADMIN_PASSWORD

Admin đầu tiên chỉ tạo được bằng lệnh này (không có tài khoản mặc định, không có mật khẩu công khai).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from .db import SessionLocal
from .models import User
from .security import hash_password, password_problem


def create_admin(email: str, name: str, password: str) -> None:
    email = email.strip().lower()
    problem = password_problem(password, email)
    if problem:
        sys.exit(f"Lỗi: {problem}")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            sys.exit("Lỗi: email này đã tồn tại.")
        db.add(User(email=email, full_name=name.strip(), role="admin", password_hash=hash_password(password)))
        db.commit()
    print(f"Đã tạo quản trị viên {email}.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):      # console Windows mặc định không in được tiếng Việt
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="server.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--password-env", help="tên biến môi trường chứa mật khẩu (dùng cho CI/triển khai)")
    a = ap.parse_args()
    if a.cmd == "create-admin":
        if a.password_env:
            pw = os.environ.get(a.password_env, "")
            if not pw:
                sys.exit(f"Lỗi: biến môi trường {a.password_env} trống.")
        else:
            pw = getpass.getpass("Mật khẩu: ")
            if pw != getpass.getpass("Nhập lại mật khẩu: "):
                sys.exit("Lỗi: hai mật khẩu không khớp.")
        create_admin(a.email, a.name, pw)


if __name__ == "__main__":
    main()
