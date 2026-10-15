"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

interface Overview {
  users_by_role: Record<string, number>; locked_users: number; doctors_pending_approval: number;
  active_assignments: number; patients_without_doctor: number; predictions_total: number; egfr_records_total: number;
  logins_last_24h: number; failed_logins_last_24h: number;
}
interface Sys { database: { ok: boolean }; model: { ready: boolean }; smtp_configured: boolean }

const Stat = ({ l, v, href }: { l: string; v: number | string; href?: string }) => (
  <div className="stat"><div className="v">{v}</div><div className="l">{href ? <Link href={href}>{l}</Link> : l}</div></div>
);

export default function AdminHome() {
  const [o, setO] = useState<Overview | null>(null);
  const [s, setS] = useState<Sys | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    Promise.all([api<Overview>("/api/admin/overview"), api<Sys>("/api/admin/system")])
      .then(([a, b]) => { setO(a); setS(b); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu."));
  }, []);
  if (err) return <Alert kind="error">{err}</Alert>;
  if (!o || !s) return <Loading />;
  return (
    <div>
      <h1>Tổng quan quản trị</h1>
      <p className="mut">Số liệu đếm trực tiếp từ cơ sở dữ liệu. Quản trị viên không xem được nội dung hồ sơ sức khỏe.</p>
      {o.doctors_pending_approval > 0 && <Alert kind="warn">Có {o.doctors_pending_approval} bác sĩ chưa được phê duyệt. <Link href="/admin/users?role=doctor">Xem tài khoản bác sĩ</Link></Alert>}
      {o.patients_without_doctor > 0 && <Alert kind="info">Có {o.patients_without_doctor} bệnh nhân chưa có bác sĩ phụ trách. <Link href="/admin/assignments">Phân công ngay</Link></Alert>}
      <h2>Tài khoản</h2>
      <div className="grid">
        <Stat l="Bệnh nhân" v={o.users_by_role.patient} href="/admin/users?role=patient" />
        <Stat l="Bác sĩ" v={o.users_by_role.doctor} href="/admin/users?role=doctor" />
        <Stat l="Quản trị viên" v={o.users_by_role.admin} href="/admin/users?role=admin" />
        <Stat l="Tài khoản đang bị khóa" v={o.locked_users} href="/admin/users?status=locked" />
      </div>
      <h2 className="mt">Hoạt động</h2>
      <div className="grid">
        <Stat l="Phân công đang hiệu lực" v={o.active_assignments} href="/admin/assignments" />
        <Stat l="Kết quả eGFR đã ghi nhận" v={o.egfr_records_total} />
        <Stat l="Lần dự đoán đã thực hiện" v={o.predictions_total} />
        <Stat l="Đăng nhập 24 giờ qua" v={o.logins_last_24h} href="/admin/audit" />
        <Stat l="Đăng nhập thất bại 24 giờ qua" v={o.failed_logins_last_24h} href="/admin/audit" />
      </div>
      <h2 className="mt">Tình trạng hệ thống</h2>
      <div className="row">
        <span className={`badge ${s.database.ok ? "b-ok" : "b-bad"}`}>Cơ sở dữ liệu: {s.database.ok ? "hoạt động" : "lỗi"}</span>
        <span className={`badge ${s.model.ready ? "b-ok" : "b-bad"}`}>Mô hình AI: {s.model.ready ? "sẵn sàng" : "chưa sẵn sàng"}</span>
        <span className={`badge ${s.smtp_configured ? "b-ok" : "b-mid"}`}>Gửi email: {s.smtp_configured ? "đã cấu hình" : "chưa cấu hình"}</span>
        <Link href="/admin/system" className="small">Chi tiết</Link>
      </div>
    </div>
  );
}
