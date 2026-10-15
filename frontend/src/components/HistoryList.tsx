"use client";

import { useEffect, useState } from "react";
import { api, ApiError, fmtDate, fmtDateTime, fmtNum } from "@/lib/api";
import type { HistoryItem } from "@/lib/types";
import PredictionView from "./PredictionView";
import { Alert, Empty, Loading, TrendBadge } from "./ui";

export default function HistoryList({ patientId, audience }: { patientId: string; audience: "patient" | "doctor" }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ items: HistoryItem[] }>(`/api/patients/${patientId}/history`)
      .then((d) => alive && setItems(d.items))
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "Không tải được lịch sử."));
    return () => { alive = false; };
  }, [patientId]);

  if (err) return <Alert kind="error">{err}</Alert>;
  if (!items) return <Loading />;
  if (items.length === 0) return <Empty>Chưa có hoạt động nào.</Empty>;

  return (
    <ul className="timeline">
      {items.map((it) => (
        <li key={`${it.type}-${it.id}`} className={`t-${it.type}`}>
          <div className="small mut">{fmtDateTime(it.at)}</div>
          {it.type === "egfr" && (
            <div>
              Ghi nhận eGFR <b>{fmtNum(it.egfr)}</b> (đo ngày {fmtDate(it.recorded_on)}) · {it.source === "doctor" ? "bác sĩ nhập" : "bệnh nhân nhập"}
              {it.replaces_id && <span className="badge b-mid" style={{ marginLeft: 6 }}>bản chỉnh sửa</span>}
              {it.voided && <span className="badge b-mid" style={{ marginLeft: 6 }}>đã được thay thế</span>}
              {it.note && <div className="small mut">{it.note}</div>}
            </div>
          )}
          {it.type === "prediction" && (
            <div>
              Dự đoán: eGFR sau 36 tháng ≈ <b>{fmtNum(it.result.forecast[it.result.forecast.length - 1].egfr)}</b> · {it.result.final_stage} · <TrendBadge name={it.result.gmm.name} />
              {it.input?.replaces_id && <span className="badge b-mid" style={{ marginLeft: 6 }}>đầu vào đã chỉnh sửa</span>}
              <div><button className="btn btn-sm" onClick={() => setOpen(open === it.id ? null : it.id)}>{open === it.id ? "Ẩn chi tiết" : "Xem chi tiết"}</button></div>
              {open === it.id && <div className="card mt"><PredictionView pred={it} audience={audience} /></div>}
            </div>
          )}
          {it.type === "note" && (
            <div>
              <b>Nhận xét của {it.doctor_name ?? "bác sĩ"}</b>: {it.body}
              {it.plan && <div className="small">Kế hoạch: {it.plan}</div>}
              {it.follow_up_on && <div className="small">Tái khám: {fmtDate(it.follow_up_on)}</div>}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
