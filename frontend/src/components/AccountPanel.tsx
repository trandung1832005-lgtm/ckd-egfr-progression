"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Alert } from "./ui";

/** Hồ sơ cá nhân (tên, năm sinh, giới tính cho bệnh nhân) và đổi mật khẩu. Dùng cho mọi vai trò. */
export default function AccountPanel() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [year, setYear] = useState(user?.profile?.birth_year?.toString() ?? "");
  const [gender, setGender] = useState(user?.profile?.gender_code?.toString() ?? "");
  const [msg, setMsg] = useState<{ k: "ok" | "error"; t: string } | null>(null);
  const [pw, setPw] = useState({ current: "", next: "", again: "" });
  const [pwMsg, setPwMsg] = useState<{ k: "ok" | "error"; t: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/me/profile", {
        method: "PUT",
        body: { full_name: name, ...(user.role === "patient" ? { birth_year: year ? Number(year) : null, gender_code: gender ? Number(gender) : null } : {}) },
      });
      await refresh();
      setMsg({ k: "ok", t: "Đã lưu thông tin." });
    } catch (ex) {
      setMsg({ k: "error", t: ex instanceof ApiError ? ex.message : "Không lưu được." });
    } finally {
      setBusy(false);
    }
  };

  const changePw = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMsg(null);
    if (pw.next !== pw.again) return setPwMsg({ k: "error", t: "Hai mật khẩu mới không khớp." });
    setBusy(true);
    try {
      await api("/api/auth/change-password", { body: { current_password: pw.current, new_password: pw.next } });
      setPw({ current: "", next: "", again: "" });
      setPwMsg({ k: "ok", t: "Đã đổi mật khẩu. Các thiết bị khác đã bị đăng xuất." });
    } catch (ex) {
      setPwMsg({ k: "error", t: ex instanceof ApiError ? ex.message : "Không đổi được mật khẩu." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid-2">
      <form className="card" onSubmit={saveProfile}>
        <h2>Thông tin tài khoản</h2>
        <p className="small mut">Email đăng nhập: {user.email}</p>
        {msg && <Alert kind={msg.k}>{msg.t}</Alert>}
        <label htmlFor="fn">Họ và tên</label>
        <input id="fn" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        {user.role === "patient" && (
          <div className="grid mt" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div><label htmlFor="by">Năm sinh</label><input id="by" type="number" min={1900} max={new Date().getFullYear()} value={year} onChange={(e) => setYear(e.target.value)} /></div>
            <div><label htmlFor="gc">Giới tính (mã dữ liệu)</label>
              <select id="gc" value={gender} onChange={(e) => setGender(e.target.value)}><option value="">–</option><option value="1">Mã 1</option><option value="2">Mã 2</option></select></div>
          </div>
        )}
        {user.role === "doctor" && user.profile && (
          <p className="small mut mt">Chuyên khoa: {user.profile.specialty ?? "–"} · Trạng thái phê duyệt: {user.profile.approved ? "đã phê duyệt" : "chưa phê duyệt"}</p>
        )}
        <p className="mt"><button className="btn btn-primary" disabled={busy}>Lưu thay đổi</button></p>
      </form>

      <form className="card" onSubmit={changePw}>
        <h2>Đổi mật khẩu</h2>
        {pwMsg && <Alert kind={pwMsg.k}>{pwMsg.t}</Alert>}
        <label htmlFor="cp">Mật khẩu hiện tại</label>
        <input id="cp" type="password" autoComplete="current-password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
        <div className="mt"><label htmlFor="np">Mật khẩu mới</label>
          <input id="np" type="password" autoComplete="new-password" required value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
          <div className="small mut">Ít nhất 10 ký tự, gồm cả chữ và số.</div></div>
        <div className="mt"><label htmlFor="np2">Nhập lại mật khẩu mới</label>
          <input id="np2" type="password" autoComplete="new-password" required value={pw.again} onChange={(e) => setPw({ ...pw, again: e.target.value })} /></div>
        <p className="mt"><button className="btn btn-primary" disabled={busy}>Đổi mật khẩu</button></p>
      </form>
    </div>
  );
}
