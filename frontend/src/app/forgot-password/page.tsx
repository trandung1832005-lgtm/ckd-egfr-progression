"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      const r = await api<{ message: string }>("/api/auth/forgot-password", { body: { email } });
      setMsg(r.message);
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không gửi được yêu cầu.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Quên mật khẩu</h1>
        <p className="mut">Nhập email tài khoản, chúng tôi sẽ gửi liên kết đặt lại mật khẩu (hiệu lực ngắn, dùng một lần).</p>
        {err && <Alert kind="error">{err}</Alert>}
        {msg && <Alert kind="ok">{msg}</Alert>}
        <label htmlFor="e">Email</label>
        <input id="e" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <p className="mt"><button className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>Gửi liên kết</button></p>
        <div className="small"><Link href="/login">Quay lại đăng nhập</Link></div>
      </form>
    </div>
  );
}
