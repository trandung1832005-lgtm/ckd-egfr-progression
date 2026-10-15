"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor, useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { Loading } from "./ui";

const NAV: Record<Role, { href: string; label: string }[]> = {
  patient: [
    { href: "/patient", label: "Tổng quan" },
    { href: "/patient/egfr", label: "Chỉ số eGFR" },
    { href: "/patient/predict", label: "Dự đoán" },
    { href: "/patient/history", label: "Lịch sử" },
    { href: "/patient/doctor", label: "Bác sĩ phụ trách" },
    { href: "/patient/profile", label: "Hồ sơ cá nhân" },
  ],
  doctor: [
    { href: "/doctor", label: "Bệnh nhân của tôi" },
    { href: "/doctor/profile", label: "Hồ sơ cá nhân" },
  ],
  admin: [
    { href: "/admin", label: "Tổng quan" },
    { href: "/admin/users", label: "Tài khoản" },
    { href: "/admin/assignments", label: "Phân công" },
    { href: "/admin/audit", label: "Nhật ký hoạt động" },
    { href: "/admin/system", label: "Hệ thống" },
  ],
};
const ROLE_LABEL: Record<Role, string> = { patient: "Bệnh nhân", doctor: "Bác sĩ", admin: "Quản trị viên" };

/** Chặn truy cập sai vai trò ở giao diện (quyền thật luôn do backend kiểm tra) và dựng khung điều hướng. */
export default function RoleShell({ role, children }: { role: Role; children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace(homeFor(user.role));
  }, [loading, user, role, router]);

  if (loading || !user || user.role !== role) return <Loading />;

  const isActive = (href: string) => (href === NAV[role][0].href ? path === href : path.startsWith(href));
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Theo dõi eGFR<small>{ROLE_LABEL[role]}</small></div>
        <nav className="nav" aria-label="Menu chính">
          {NAV[role].map((n) => (
            <Link key={n.href} href={n.href} aria-current={isActive(n.href) ? "page" : undefined}>{n.label}</Link>
          ))}
        </nav>
        <div className="side-foot">
          <div>{user.full_name}</div>
          <button className="btn btn-sm" onClick={async () => { await logout(); router.replace("/login"); }}>Đăng xuất</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
