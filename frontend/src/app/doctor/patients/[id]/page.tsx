"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RecordsChart } from "@/components/charts";
import HistoryList from "@/components/HistoryList";
import PredictionForm from "@/components/PredictionForm";
import PredictionView from "@/components/PredictionView";
import RecordsPanel from "@/components/RecordsPanel";
import { Alert, Empty, Loading } from "@/components/ui";
import { api, ApiError, fmtDate, fmtDateTime, fmtNum } from "@/lib/api";
import type { EgfrRecord, Note, Prediction } from "@/lib/types";

interface Detail {
  id: string; full_name: string; email: string | null;
  profile: { birth_year: number | null; gender_code: number | null };
  egfr_count: number; latest_egfr: EgfrRecord | null; latest_prediction: Prediction | null;
}
type Tab = "overview" | "egfr" | "predict" | "history" | "notes";
const TABS: [Tab, string][] = [["overview", "Tổng quan"], ["egfr", "Chỉ số eGFR"], ["predict", "Dự đoán"], ["history", "Lịch sử"], ["notes", "Nhận xét & kế hoạch"]];

function NotesTab({ pid, lastPredId }: { pid: string; lastPredId: string | null }) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [f, setF] = useState({ body: "", plan: "", follow_up_on: "", attach: true });
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setNotes((await api<{ notes: Note[] }>(`/api/patients/${pid}/notes`)).notes); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Không tải được nhận xét."); }
  }, [pid]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- nạp dữ liệu khi mở tab
    void load();
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(""); setOk("");
    try {
      await api(`/api/patients/${pid}/notes`, { body: {
        body: f.body, plan: f.plan || null, follow_up_on: f.follow_up_on || null,
        prediction_id: f.attach && lastPredId ? lastPredId : null } });
      setF({ body: "", plan: "", follow_up_on: "", attach: true });
      setOk("Đã lưu nhận xét.");
      await load();
    } catch (ex) { setErr(ex instanceof ApiError ? ex.message : "Không lưu được."); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <form onSubmit={submit}>
        <p className="small mut">Nhận xét chuyên môn của bác sĩ, tách biệt với kết quả mô hình và không làm thay đổi kết quả dự đoán. Bệnh nhân không xem được mục này.</p>
        <label htmlFor="nb">Nhận xét</label>
        <textarea id="nb" required maxLength={4000} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
        <div className="grid mt">
          <div><label htmlFor="np">Kế hoạch theo dõi</label><input id="np" value={f.plan} onChange={(e) => setF({ ...f, plan: e.target.value })} /></div>
          <div><label htmlFor="nf">Lịch tái khám</label><input id="nf" type="date" value={f.follow_up_on} onChange={(e) => setF({ ...f, follow_up_on: e.target.value })} /></div>
        </div>
        {lastPredId && (
          <label className="mt" style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--ink)" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={f.attach} onChange={(e) => setF({ ...f, attach: e.target.checked })} /> Gắn với dự đoán gần nhất
          </label>
        )}
        {err && <Alert kind="error">{err}</Alert>}
        {ok && <Alert kind="ok">{ok}</Alert>}
        <p className="mt"><button className="btn btn-primary" disabled={busy}>Lưu nhận xét</button></p>
      </form>
      <h3>Nhận xét đã ghi</h3>
      {!notes ? <Loading /> : notes.length === 0 ? <Empty>Chưa có nhận xét nào.</Empty> : (
        <ul className="timeline">
          {notes.map((n) => (
            <li key={n.id} className="t-note">
              <div className="small mut">{fmtDateTime(n.created_at)} · {n.doctor_name ?? "Bác sĩ"}</div>
              <div>{n.body}</div>
              {n.plan && <div className="small">Kế hoạch: {n.plan}</div>}
              {n.follow_up_on && <div className="small">Tái khám: {fmtDate(n.follow_up_on)}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DoctorPatient() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Detail | null>(null);
  const [recs, setRecs] = useState<EgfrRecord[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [err, setErr] = useState("");
  const [fresh, setFresh] = useState<Prediction | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [a, b] = await Promise.all([api<Detail>(`/api/patients/${id}`), api<{ records: EgfrRecord[] }>(`/api/patients/${id}/egfr`)]);
        if (alive) { setD(a); setRecs(b.records); setErr(""); }
      } catch (e) {
        if (alive) setErr(e instanceof ApiError ? e.message : "Không tải được hồ sơ.");
      }
    })();
    return () => { alive = false; };
  }, [id, version, tab]);

  if (err) return <><Alert kind="error">{err}</Alert><Link className="btn" href="/doctor">← Quay lại danh sách</Link></>;
  if (!d) return <Loading />;
  const lp = fresh ?? d.latest_prediction;

  return (
    <div>
      <p className="small"><Link href="/doctor">← Danh sách bệnh nhân</Link></p>
      <h1>{d.full_name}</h1>
      <p className="mut small">{d.email}{d.profile.birth_year ? ` · sinh năm ${d.profile.birth_year}` : ""}{d.profile.gender_code ? ` · giới tính mã ${d.profile.gender_code}` : ""}</p>
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>)}
      </div>

      {tab === "overview" && (
        <div>
          <div className="grid">
            <div className="stat"><div className="l">eGFR đo gần nhất</div><div className="v">{d.latest_egfr ? fmtNum(d.latest_egfr.egfr) : "–"}</div><div className="small mut">{d.latest_egfr ? fmtDate(d.latest_egfr.recorded_on) : "chưa có dữ liệu"}</div></div>
            <div className="stat"><div className="l">Số kết quả đã ghi nhận</div><div className="v">{d.egfr_count}</div></div>
            <div className="stat"><div className="l">Dự đoán gần nhất</div><div className="v">{lp ? fmtDate(lp.created_at) : "–"}</div></div>
          </div>
          <div className="card mt"><h2>Diễn biến eGFR đã đo</h2>{recs.length ? <RecordsChart records={recs} /> : <Empty>Chưa có kết quả eGFR.</Empty>}</div>
          <div className="card"><h2>Dự đoán gần nhất</h2>
            {lp ? <PredictionView pred={lp} audience="doctor" /> : <Empty>Chưa có dự đoán. Mở tab “Dự đoán” để thực hiện.</Empty>}
          </div>
        </div>
      )}
      {tab === "egfr" && <div className="card"><RecordsPanel patientId={id} /></div>}
      {tab === "predict" && (
        <div className="card">
          {fresh ? (
            <>
              <h2>Kết quả dự đoán</h2>
              <PredictionView pred={fresh} audience="doctor" />
              <p className="mt"><button className="btn" onClick={() => { setFresh(null); setVersion((v) => v + 1); }}>Thực hiện dự đoán khác</button></p>
            </>
          ) : <PredictionForm patientId={id} onCreated={(p) => { setFresh(p); setVersion((v) => v + 1); }} />}
        </div>
      )}
      {tab === "history" && <div className="card"><HistoryList key={version} patientId={id} audience="doctor" /></div>}
      {tab === "notes" && <div className="card"><NotesTab pid={id} lastPredId={lp?.id ?? null} /></div>}
    </div>
  );
}
