"use client";

import { useEffect, useState } from "react";
import { Alert, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

interface Sys {
  api: string; database: { ok: boolean; kind: string };
  model: { ready: boolean; version: string | null; torch: string | null; gmm: { K: number; covariance: string } | null };
  smtp_configured: boolean; env: string; allowed_origins: string[]; cookie_secure: boolean; session_ttl_hours: number;
}

const Row = ({ k, children }: { k: string; children: React.ReactNode }) => <tr><td className="mut" style={{ width: 240 }}>{k}</td><td>{children}</td></tr>;

export default function AdminSystem() {
  const [s, setS] = useState<Sys | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<Sys>("/api/admin/system").then(setS).catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu.")); }, []);
  if (err) return <Alert kind="error">{err}</Alert>;
  if (!s) return <Loading />;
  const b = (ok: boolean, yes: string, no: string) => <span className={`badge ${ok ? "b-ok" : "b-bad"}`}>{ok ? yes : no}</span>;
  return (
    <div>
      <h1>Hệ thống</h1>
      <p className="mut">Tình trạng API, cơ sở dữ liệu và mô hình AI. Không hiển thị bí mật hay chuỗi kết nối.</p>
      <div className="card tw">
        <table><tbody>
          <Row k="API">{b(s.api === "ok", "Hoạt động", "Lỗi")}</Row>
          <Row k="Cơ sở dữ liệu">{b(s.database.ok, "Hoạt động", "Lỗi kết nối")} <span className="small mut">({s.database.kind})</span></Row>
          <Row k="Mô hình AI">{b(s.model.ready, "Sẵn sàng", "Chưa sẵn sàng")}{s.model.version && <span className="small mut"> · phiên bản {s.model.version}</span>}</Row>
          {s.model.gmm && <Row k="Phân nhóm xu hướng">K = {s.model.gmm.K}, covariance = {s.model.gmm.covariance}</Row>}
          <Row k="Gửi email">{b(s.smtp_configured, "Đã cấu hình", "Chưa cấu hình")}{!s.smtp_configured && <span className="small mut"> · liên kết đặt mật khẩu sẽ hiển thị cho quản trị viên</span>}</Row>
          <Row k="Môi trường">{s.env}{s.env !== "prod" && <span className="small mut"> (cookie chưa bật Secure)</span>}</Row>
          <Row k="Thời hạn phiên đăng nhập">{s.session_ttl_hours} giờ</Row>
          <Row k="Domain được phép gọi API">{s.allowed_origins.join(", ")}</Row>
        </tbody></table>
      </div>
    </div>
  );
}
