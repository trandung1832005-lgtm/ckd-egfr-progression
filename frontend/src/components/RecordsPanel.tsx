"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, fmtDate, fmtNum } from "@/lib/api";
import type { EgfrRecord } from "@/lib/types";
import { RecordsChart } from "./charts";
import { Alert, Empty, Loading } from "./ui";

const today = () => new Date().toISOString().slice(0, 10);

export default function RecordsPanel({ patientId }: { patientId: string }) {
  const [rows, setRows] = useState<EgfrRecord[] | null>(null);
  const [all, setAll] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [form, setForm] = useState({ recorded_on: today(), egfr: "", note: "" });
  const [editing, setEditing] = useState<string | null>(null);
  const [edit, setEdit] = useState({ recorded_on: "", egfr: "", note: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows((await api<{ records: EgfrRecord[] }>(`/api/patients/${patientId}/egfr${all ? "?include_voided=true" : ""}`)).records);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu.");
    }
  }, [patientId, all]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- nạp dữ liệu khi mở/đổi bộ lọc
    void load();
  }, [load]);

  const save = async (path: string, v: typeof form) => {
    setBusy(true); setErr(""); setOk("");
    try {
      await api(path, { body: { recorded_on: v.recorded_on, egfr: Number(v.egfr), note: v.note.trim() || null } });
      setOk("Đã lưu.");
      await load();
      return true;
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không lưu được.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!rows) return err ? <Alert kind="error">{err}</Alert> : <Loading />;
  const active = rows.filter((r) => !r.voided);

  return (
    <div>
      {active.length > 0 ? <RecordsChart records={active} /> : <Empty>Chưa có kết quả eGFR nào. Hãy thêm kết quả đo đầu tiên bên dưới.</Empty>}

      <h3>Thêm kết quả đo</h3>
      <form className="grid" onSubmit={async (e) => { e.preventDefault(); if (await save(`/api/patients/${patientId}/egfr`, form)) setForm({ ...form, egfr: "", note: "" }); }}>
        <div><label htmlFor="d">Ngày đo</label><input id="d" type="date" max={today()} required value={form.recorded_on} onChange={(e) => setForm({ ...form, recorded_on: e.target.value })} /></div>
        <div><label htmlFor="v">eGFR (mL/phút/1,73 m²)</label><input id="v" type="number" step="any" min="0.1" max="200" required value={form.egfr} onChange={(e) => setForm({ ...form, egfr: e.target.value })} /></div>
        <div><label htmlFor="n">Ghi chú (tùy chọn)</label><input id="n" maxLength={300} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></div>
        <div style={{ alignSelf: "end" }}><button className="btn btn-primary" disabled={busy}>Lưu kết quả</button></div>
      </form>
      {err && <Alert kind="error">{err}</Alert>}
      {ok && <Alert kind="ok">{ok}</Alert>}

      <div className="row mt">
        <h3 style={{ margin: 0 }}>Danh sách kết quả</h3>
        <span className="spacer" />
        <label style={{ margin: 0, display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" style={{ width: "auto" }} checked={all} onChange={(e) => setAll(e.target.checked)} /> Hiện cả bản đã được thay thế
        </label>
      </div>
      <p className="small mut">Khi sửa một kết quả, hệ thống tạo bản mới và giữ lại bản cũ trong lịch sử.</p>
      <div className="tw">
        <table>
          <thead><tr><th>Ngày đo</th><th className="num">eGFR</th><th>Nguồn</th><th>Ghi chú</th><th /></tr></thead>
          <tbody>
            {[...rows].reverse().map((r) => editing === r.id ? (
              <tr key={r.id}>
                <td><input type="date" max={today()} value={edit.recorded_on} onChange={(e) => setEdit({ ...edit, recorded_on: e.target.value })} /></td>
                <td><input type="number" step="any" value={edit.egfr} onChange={(e) => setEdit({ ...edit, egfr: e.target.value })} /></td>
                <td colSpan={2}><input value={edit.note} maxLength={300} onChange={(e) => setEdit({ ...edit, note: e.target.value })} /></td>
                <td className="row">
                  <button className="btn btn-primary btn-sm" disabled={busy} onClick={async () => { if (await save(`/api/patients/${patientId}/egfr/${r.id}/replace`, edit)) setEditing(null); }}>Lưu bản mới</button>
                  <button className="btn btn-sm" onClick={() => setEditing(null)}>Hủy</button>
                </td>
              </tr>
            ) : (
              <tr key={r.id} style={r.voided ? { color: "var(--mut)", textDecoration: "line-through" } : undefined}>
                <td>{fmtDate(r.recorded_on)}</td><td className="num">{fmtNum(r.egfr)}</td>
                <td>{r.source === "doctor" ? "Bác sĩ" : "Bệnh nhân"}</td><td>{r.note ?? ""}{r.voided ? " (đã được thay thế)" : ""}</td>
                <td>{!r.voided && <button className="btn btn-sm" onClick={() => { setEditing(r.id); setEdit({ recorded_on: r.recorded_on, egfr: String(r.egfr), note: r.note ?? "" }); }}>Sửa</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
