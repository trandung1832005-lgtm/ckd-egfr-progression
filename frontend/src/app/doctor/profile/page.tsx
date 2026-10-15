"use client";

import AccountPanel from "@/components/AccountPanel";

export default function DoctorProfile() {
  return (
    <div>
      <h1>Hồ sơ cá nhân</h1>
      <p className="mut">Quản lý thông tin tài khoản và mật khẩu.</p>
      <AccountPanel />
    </div>
  );
}
