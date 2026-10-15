"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Alert, ConfirmDialog, Empty, Loading } from "@/components/ui";
import { api, ApiError, fmtDateTime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AdminUser, Role } from "@/lib/types";

const ROLE_LABEL: Record<string, string> = { patient: "Bệnh nhân", doctor: "Bác sĩ", admin: "Quản trị viên" };

type Pending = { title: string; message: string; danger?: boolean; run: () => Promise<void> };

function UsersInner() {
  const sp = useSearchParams();
  const { user: me } = useAuth();
  const [role, setRole] = useState(sp.get("role") ?? "");
  const [status, setStatus] = useState(sp.get("status") ?? "");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<AdminUser[] | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [show, setShow] = useState(false);
  const [nu, setNu] = useState({ email: "", full_name: "", role: "doctor" as Role, specialty: "" });

  const load = useCallback(async () => {
    const p = new URLSearchParams();
    if (role) p.set("role", role);
    if (status) p.set("status", status);
    if (q.trim()) p.set("q", q.trim());
    try { setRows((await api<{ users: AdminUser[] }>(`/api/admin/users?${p}`)).users); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Không tải được danh sách."); }
  }, [role, status, q]);
  useEffect(() => {
    const t = setTimeout(() => void load(), 250);
    return () => clearTimeout(t);
  }, [load]);

  const act = (fn: () => Promise<void>) => async () => {
    setPending(null);
    try { await fn(); await load(); } catch (e) { setErr(e instanceof ApiError ? e.message : "Thao tác không thành công."); }
  };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(""); setNote(null);
    try {
      const r = await api<{ email_sent: boolean; invite_link?: string }>("/api/admin/users", {
        body: { email: nu.email, full_name: nu.full_name, role: nu.role, specialty: nu.role === "doctor" ? nu.specialty || null : null } });
      setNote(r.email_sent
        ? { kind: "ok", text: "Đã tạo tài khoản và gửi email kích hoạt." }
        : { kind: "warn", text: `Đã tạo tài khoản. Chưa cấu hình email, hãy gửi liên kết kích hoạt này cho người dùng (chỉ hiển thị một lần, hiệu lực 72 giờ): ${r.invite_link}` });
      setNu({ email: "", full_name: "", role: "doctor", specialty: "" });
      await load();
    } catch (ex) { setErr(ex instanceof ApiError ? ex.message : "Không tạo được tài khoản."); }
  };

  return (
    <div>
      <div className="row"><h1 style={{ margin: 0 }}>Quản lý tài khoản</h1><span className="spacer" /><button className="btn btn-primary" onClick={() => setShow(!show)}>{show ? "Đóng" : "+ Tạo tài khoản"}</button></div>
      <p className="mut">Bác sĩ và quản trị viên chỉ được tạo tại đây. Người dùng tự đặt mật khẩu qua liên kết kích hoạt, không có mật khẩu mặc định.</p>
      {note && <Alert kind={note.kind}><span style={{ wordBreak: "break-all" }}>{note.text}</span></Alert>}
      {err && <Alert kind="error">{err}</Alert>}

      {show && (
        <form className="card" onSubmit={create}>
          <h2>Tạo tài khoản mới</h2>
          <div className="grid">
            <div><label htmlFor="ne">Email</label><input id="ne" type="email" required value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} /></div>
            <div><label htmlFor="nn">Họ và tên</label><input id="nn" required maxLength={120} value={nu.full_name} onChange={(e) => setNu({ ...nu, full_name: e.target.value })} /></div>
            <div><label htmlFor="nr">Vai trò</label>
              <select id="nr" value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value as Role })}>
                <option value="doctor">Bác sĩ</option><option value="patient">Bệnh nhân</option><option value="admin">Quản trị viên</option></select></div>
            {nu.role === "doctor" && <div><label htmlFor="ns">Chuyên khoa (tùy chọn)</label><input id="ns" maxLength={120} value={nu.specialty} onChange={(e) => setNu({ ...nu, specialty: e.target.value })} /></div>}
          </div>
          {nu.role === "admin" && <Alert kind="warn">Quản trị viên mới có toàn quyền quản trị tài khoản. Chỉ tạo khi thật sự cần.</Alert>}
          <p className="mt"><button className="btn btn-primary">Tạo và gửi liên kết kích hoạt</button></p>
        </form>
      )}

      <div className="card">
        <div className="grid">
          <div><label htmlFor="fr">Vai trò</label><select id="fr" value={role} onChange={(e) => setRole(e.target.value)}><option value="">Tất cả</option><option value="patient">Bệnh nhân</option><option value="doctor">Bác sĩ</option><option value="admin">Quản trị viên</option></select></div>
          <div><label htmlFor="fs">Trạng thái</label><select id="fs" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Tất cả</option><option value="active">Đang hoạt động</option><option value="locked">Đã khóa</option></select></div>
          <div><label htmlFor="fq">Tìm kiếm</label><input id="fq" value={q} maxLength={80} onChange={(e) => setQ(e.target.value)} placeholder="Tên hoặc email" /></div>
        </div>
      </div>

      {!rows && !err && <Loading />}
      {rows && rows.length === 0 && <Empty>Không có tài khoản nào khớp bộ lọc.</Empty>}
      {rows && rows.length > 0 && (
        <div className="card tw">
          <table>
            <thead><tr><th>Họ tên</th><th>Vai trò</th><th>Trạng thái</th><th>Đăng nhập gần nhất</th><th /></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <td><b>{u.full_name}</b><div className="small mut">{u.email}</div></td>
                  <td>{ROLE_LABEL[u.role]}{u.role === "doctor" && <div className="small mut">{u.doctor?.approved ? "Đã phê duyệt" : "Chưa phê duyệt"}{u.doctor?.specialty ? ` · ${u.doctor.specialty}` : ""}</div>}</td>
                  <td><span className={`badge ${u.status === "active" ? "b-ok" : "b-bad"}`}>{u.status === "active" ? "Hoạt động" : "Đã khóa"}</span></td>
                  <td className="small">{fmtDateTime(u.last_login_at)}</td>
                  <td>
                    <div className="row">
                      {u.id !== me?.id && (u.status === "active"
                        ? <button className="btn btn-danger btn-sm" onClick={() => setPending({ title: "Khóa tài khoản", danger: true, message: `Khóa tài khoản ${u.full_name}? Người này sẽ bị đăng xuất ngay và không đăng nhập được cho đến khi mở khóa.`,
                            run: act(async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { status: "locked" } }); }) })}>Khóa</button>
                        : <button className="btn btn-sm" onClick={act(async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { status: "active" } }); })}>Mở khóa</button>)}
                      {u.role === "doctor" && (
                        <button className="btn btn-sm" onClick={() => setPending({ title: u.doctor?.approved ? "Thu hồi phê duyệt" : "Phê duyệt bác sĩ", danger: !!u.doctor?.approved,
                          message: u.doctor?.approved ? `Thu hồi phê duyệt của ${u.full_name}? Bác sĩ sẽ mất quyền xem hồ sơ bệnh nhân ngay lập tức.` : `Phê duyệt ${u.full_name}?`,
                          run: act(async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { approved: !u.doctor?.approved } }); }) })}>
                          {u.doctor?.approved ? "Thu hồi phê duyệt" : "Phê duyệt"}</button>)}
                      <button className="btn btn-sm" onClick={() => setPending({ title: "Tạo liên kết đặt lại mật khẩu", message: `Tạo liên kết đặt lại mật khẩu cho ${u.full_name}? Các liên kết cũ sẽ mất hiệu lực.`,
                        run: act(async () => {
                          const r = await api<{ email_sent: boolean; reset_link?: string }>(`/api/admin/users/${u.id}/reset-link`, { method: "POST" });
                          setNote(r.email_sent ? { kind: "ok", text: "Đã gửi email đặt lại mật khẩu." } : { kind: "warn", text: `Chưa cấu hình email. Hãy gửi liên kết này cho người dùng (hiệu lực ngắn, dùng một lần): ${r.reset_link}` });
                        }) })}>Đặt lại MK</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pending && <ConfirmDialog title={pending.title} message={pending.message} danger={pending.danger} onConfirm={pending.run} onCancel={() => setPending(null)} />}
    </div>
  );
}

export default function AdminUsers() {
  return <Suspense fallback={<Loading />}><UsersInner /></Suspense>;
}
