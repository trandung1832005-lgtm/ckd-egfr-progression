"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RecordsChart } from "@/components/charts";
import { Alert, Empty, Loading, TrendBadge } from "@/components/ui";
import { api, ApiError, fmtDate, fmtDateTime, fmtNum } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EgfrRecord, Prediction } from "@/lib/types";

interface Detail { egfr_count: number; latest_egfr: EgfrRecord | null; latest_prediction: Prediction | null }

export default function PatientHome() {
  const { user } = useAuth();
  const [d, setD] = useState<Detail | null>(null);
  const [recs, setRecs] = useState<EgfrRecord[]>([]);
  const [docs, setDocs] = useState<number | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!user) return;
    let alive = true;
    (async () => {
      try {
        const [a, b, c] = await Promise.all([
          api<Detail>(`/api/patients/${user.id}`),
          api<{ records: EgfrRecord[] }>(`/api/patients/${user.id}/egfr`),
          api<{ doctors: unknown[] }>(`/api/patients/${user.id}/doctors`),
        ]);
        if (alive) { setD(a); setRecs(b.records); setDocs(c.doctors.length); }
      } catch (e) {
        if (alive) setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu.");
      }
    })();
    return () => { alive = false; };
  }, [user]);

  if (err) return <Alert kind="error">{err}</Alert>;
  if (!d || !user) return <Loading />;
  const p = d.latest_prediction;
  const last = p?.result.forecast[p.result.forecast.length - 1];

  return (
    <div>
      <h1>Xin chào, {user.full_name}</h1>
      <p className="mut">Tổng quan tình trạng theo dõi của bạn.</p>

      {d.egfr_count === 0 && <Alert kind="info">Bạn chưa có kết quả eGFR nào. Hãy <Link href="/patient/egfr">thêm kết quả đo</Link> để bắt đầu theo dõi.</Alert>}
      {docs === 0 && <Alert kind="info">Bạn chưa được phân công bác sĩ phụ trách. Quản trị viên sẽ phân công bác sĩ cho bạn.</Alert>}

      <div className="grid">
        <div className="stat"><div className="l">eGFR đo gần nhất</div><div className="v">{d.latest_egfr ? fmtNum(d.latest_egfr.egfr) : "–"}</div>
          <div className="small mut">{d.latest_egfr ? `ngày ${fmtDate(d.latest_egfr.recorded_on)}` : "chưa có dữ liệu"}</div></div>
        <div className="stat"><div className="l">Số kết quả đã ghi nhận</div><div className="v">{d.egfr_count}</div></div>
        <div className="stat"><div className="l">Dự đoán gần nhất</div>
          <div className="v">{last ? fmtNum(last.egfr) : "–"}</div>
          <div className="small mut">{p ? `eGFR dự đoán sau 36 tháng · ${fmtDateTime(p.created_at)}` : "chưa có dự đoán"}</div></div>
        <div className="stat"><div className="l">Bác sĩ phụ trách</div><div className="v">{docs ?? "–"}</div></div>
      </div>

      <div className="card mt">
        <h2>Diễn biến eGFR đã đo</h2>
        {recs.length > 0 ? <RecordsChart records={recs} /> : <Empty>Chưa có dữ liệu để vẽ biểu đồ.</Empty>}
      </div>

      <div className="card">
        <h2>Kết quả dự đoán mới nhất</h2>
        {p ? (
          <>
            <p>eGFR dự đoán sau 36 tháng khoảng <b>{fmtNum(last!.egfr)}</b> · mức tham chiếu {p.result.final_stage} · <TrendBadge name={p.result.gmm.name} /></p>
            <Link className="btn" href="/patient/history">Xem chi tiết trong Lịch sử</Link>
          </>
        ) : <Empty>Bạn chưa thực hiện dự đoán nào. <Link href="/patient/predict">Thực hiện dự đoán</Link></Empty>}
        <p className="small mut mt">Kết quả dự đoán chỉ mang tính tham khảo, không phải chẩn đoán. Hãy trao đổi với bác sĩ về tình trạng của bạn.</p>
      </div>
    </div>
  );
}
