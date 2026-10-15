"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";

export default function RegisterPage() {
  const { setUser } = useAuth();
  const router = useRouter();
  const [f, setF] = useState({ full_name: "", email: "", password: "", birth_year: "", gender_code: "", consent: false });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF({ ...f, [k]: v });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const me = await api<Me>("/api/auth/register", {
        body: {
          full_name: f.full_name, email: f.email, password: f.password, consent: f.consent,
          birth_year: f.birth_year ? Number(f.birth_year) : null,
          gender_code: f.gender_code ? Number(f.gender_code) : null,
        },
      });
      setUser(me);
      router.replace(homeFor(me.role));
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không đăng ký được.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Tạo tài khoản bệnh nhân</h1>
        <p className="mut small">Tài khoản bác sĩ và quản trị viên do quản trị viên tạo, không đăng ký tại đây.</p>
        {err && <Alert kind="error">{err}</Alert>}
        <div><label htmlFor="n">Họ và tên</label><input id="n" required maxLength={120} value={f.full_name} onChange={(e) => set("full_name", e.target.value)} /></div>
        <div className="mt"><label htmlFor="e">Email</label><input id="e" type="email" autoComplete="username" required value={f.email} onChange={(e) => set("email", e.target.value)} /></div>
        <div className="mt"><label htmlFor="p">Mật khẩu</label><input id="p" type="password" autoComplete="new-password" required value={f.password} onChange={(e) => set("password", e.target.value)} />
          <div className="small mut">Ít nhất 10 ký tự, gồm cả chữ và số.</div></div>
        <div className="grid mt" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div><label htmlFor="y">Năm sinh (tùy chọn)</label><input id="y" type="number" min={1900} max={new Date().getFullYear()} value={f.birth_year} onChange={(e) => set("birth_year", e.target.value)} /></div>
          <div><label htmlFor="g">Giới tính (mã dữ liệu, tùy chọn)</label>
            <select id="g" value={f.gender_code} onChange={(e) => set("gender_code", e.target.value)}><option value="">–</option><option value="1">Mã 1</option><option value="2">Mã 2</option></select></div>
        </div>
        <label className="mt" style={{ display: "flex", gap: 8, alignItems: "flex-start", color: "var(--ink)" }}>
          <input type="checkbox" style={{ width: "auto", marginTop: 4 }} checked={f.consent} onChange={(e) => set("consent", e.target.checked)} required />
          <span>Tôi đồng ý để hệ thống lưu và xử lý dữ liệu sức khỏe của tôi (eGFR, thông tin lâm sàng) nhằm theo dõi và dự đoán xu hướng. Chỉ bác sĩ được phân công cho tôi mới xem được dữ liệu này.</span>
        </label>
        <p className="mt"><button className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>{busy ? "Đang tạo…" : "Tạo tài khoản"}</button></p>
        <div className="small"><Link href="/login">Đã có tài khoản? Đăng nhập</Link></div>
      </form>
    </div>
  );
}
