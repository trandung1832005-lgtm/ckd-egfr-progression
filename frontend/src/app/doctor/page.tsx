"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Empty, Loading, TrendBadge } from "@/components/ui";
import { api, ApiError, fmtDate, fmtDateTime, fmtNum } from "@/lib/api";

interface Row {
  id: string; full_name: string; email: string;
  latest_egfr: { egfr: number; recorded_on: string } | null;
  latest_prediction: { id: string; created_at: string; final_stage: string; trend: string } | null;
}

export default function DoctorHome() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api<{ patients: Row[] }>(`/api/doctor/patients${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`)
        .then((d) => { if (alive) { setRows(d.patients); setErr(""); } })
        .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "Không tải được danh sách."); });
    }, 250);                                       // đợi người dùng gõ xong rồi mới gọi API
    return () => { alive = false; clearTimeout(t); };
  }, [q]);

  return (
    <div>
      <h1>Bệnh nhân của tôi</h1>
      <p className="mut">Chỉ hiển thị những bệnh nhân đã được quản trị viên phân công cho bạn.</p>
      <div className="card">
        <label htmlFor="q">Tìm theo tên hoặc email</label>
        <input id="q" value={q} maxLength={80} onChange={(e) => setQ(e.target.value)} placeholder="Nhập để tìm…" />
      </div>
      {err && <Alert kind="error">{err}</Alert>}
      {!rows && !err && <Loading />}
      {rows && rows.length === 0 && !err && (
        <Empty>{q.trim() ? "Không có bệnh nhân nào khớp với từ khóa." : "Bạn chưa được phân công bệnh nhân nào."}</Empty>
      )}
      {rows && rows.length > 0 && (
        <div className="card tw">
          <table>
            <thead><tr><th>Bệnh nhân</th><th>eGFR đo gần nhất</th><th>Dự đoán gần nhất</th><th /></tr></thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td><b>{p.full_name}</b><div className="small mut">{p.email}</div></td>
                  <td>{p.latest_egfr ? <>{fmtNum(p.latest_egfr.egfr)} <span className="small mut">({fmtDate(p.latest_egfr.recorded_on)})</span></> : <span className="mut">Chưa có</span>}</td>
                  <td>{p.latest_prediction
                    ? <><TrendBadge name={p.latest_prediction.trend} /> <span className="small">{p.latest_prediction.final_stage}</span><div className="small mut">{fmtDateTime(p.latest_prediction.created_at)}</div></>
                    : <span className="mut">Chưa có</span>}</td>
                  <td><Link className="btn btn-sm" href={`/doctor/patients/${p.id}`}>Mở hồ sơ</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
