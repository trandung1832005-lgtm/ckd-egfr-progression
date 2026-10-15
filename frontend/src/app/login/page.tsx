"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";

export default function LoginPage() {
  const { user, loading, setUser } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace(homeFor(user.role));
  }, [loading, user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const me = await api<Me>("/api/auth/login", { body: { email, password } });
      setUser(me);
      router.replace(homeFor(me.role));
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không đăng nhập được.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Theo dõi chức năng thận</h1>
        <p className="mut">Đăng nhập để xem chỉ số eGFR và kết quả dự đoán.</p>
        {err && <Alert kind="error">{err}</Alert>}
        <div><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="mt"><label htmlFor="pw">Mật khẩu</label><input id="pw" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <p className="mt"><button className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>{busy ? "Đang đăng nhập…" : "Đăng nhập"}</button></p>
        <div className="row small"><Link href="/forgot-password">Quên mật khẩu?</Link><span className="spacer" /><Link href="/register">Tạo tài khoản bệnh nhân</Link></div>
      </form>
    </div>
  );
}
