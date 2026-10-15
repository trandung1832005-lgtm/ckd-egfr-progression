"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (pw !== pw2) return setErr("Hai mật khẩu không khớp.");
    setBusy(true);
    try {
      await api("/api/auth/reset-password", { body: { token, new_password: pw } });
      setDone(true);
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không đặt lại được mật khẩu.");
    } finally {
      setBusy(false);
    }
  };

  if (!token) return <Alert kind="error">Liên kết không hợp lệ. Hãy yêu cầu liên kết mới.</Alert>;
  if (done) {
    return (
      <>
        <Alert kind="ok">Đã đặt mật khẩu mới. Các phiên đăng nhập cũ đã bị đăng xuất.</Alert>
        <Link className="btn btn-primary" href="/login">Đăng nhập</Link>
      </>
    );
  }
  return (
    <form onSubmit={submit}>
      {err && <Alert kind="error">{err}</Alert>}
      <label htmlFor="p">Mật khẩu mới</label>
      <input id="p" type="password" autoComplete="new-password" required value={pw} onChange={(e) => setPw(e.target.value)} />
      <div className="small mut">Ít nhất 10 ký tự, gồm cả chữ và số.</div>
      <div className="mt"><label htmlFor="p2">Nhập lại mật khẩu</label><input id="p2" type="password" autoComplete="new-password" required value={pw2} onChange={(e) => setPw2(e.target.value)} /></div>
      <p className="mt"><button className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>Đặt mật khẩu</button></p>
    </form>
  );
}

export default function ResetPage() {
  return (
    <div className="center-page">
      <div className="card auth-card">
        <h1>Đặt mật khẩu</h1>
        <Suspense fallback={<Loading />}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  );
}
