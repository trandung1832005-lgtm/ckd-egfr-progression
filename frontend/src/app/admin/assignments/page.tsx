"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, ConfirmDialog, Empty, Loading } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

interface Assignment {
  id: string; created_at: string; ended_at: string | null;
  doctor: { id: string; full_name: string | null }; patient: { id: string; full_name: string | null };
}

export default function AdminAssignments() {
  const [rows, setRows] = useState<Assignment[] | null>(null);
  const [doctors, setDoctors] = useState<AdminUser[]>([]);
  const [patients, setPatients] = useState<AdminUser[]>([]);
  const [sel, setSel] = useState({ doctor_id: "", patient_id: "" });
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [del, setDel] = useState<Assignment | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, d, p] = await Promise.all([
        api<{ assignments: Assignment[] }>("/api/admin/assignments?active=true"),
        api<{ users: AdminUser[] }>("/api/admin/users?role=doctor&status=active&limit=500"),
        api<{ users: AdminUser[] }>("/api/admin/users?role=patient&status=active&limit=500"),
      ]);
      setRows(a.assignments);
      setDoctors(d.users.filter((u) => u.doctor?.approved));
      setPatients(p.users);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu."); }
  }, []);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- nạp dữ liệu khi mở trang
    void load();
  }, [load]);

  const assign = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(""); setOk("");
    try { await api("/api/admin/assignments", { body: sel }); setOk("Đã phân công."); setSel({ doctor_id: "", patient_id: "" }); await load(); }
    catch (ex) { setErr(ex instanceof ApiError ? ex.message : "Không phân công được."); }
  };
  const end = async () => {
    const a = del; setDel(null);
    if (!a) return;
    try { await api(`/api/admin/assignments/${a.id}`, { method: "DELETE" }); setOk("Đã hủy phân công. Bác sĩ mất quyền truy cập ngay."); await load(); }
    catch (ex) { setErr(ex instanceof ApiError ? ex.message : "Không hủy được."); }
  };

  return (
    <div>
      <h1>Phân công bác sĩ – bệnh nhân</h1>
      <p className="mut">Bác sĩ chỉ xem được hồ sơ của bệnh nhân đang được phân công. Hủy phân công có hiệu lực ngay.</p>
      {err && <Alert kind="error">{err}</Alert>}
      {ok && <Alert kind="ok">{ok}</Alert>}
      <form className="card" onSubmit={assign}>
        <h2>Phân công mới</h2>
        <div className="grid">
          <div><label htmlFor="d">Bác sĩ (đã phê duyệt)</label>
            <select id="d" required value={sel.doctor_id} onChange={(e) => setSel({ ...sel, doctor_id: e.target.value })}>
              <option value="">– Chọn bác sĩ –</option>{doctors.map((d) => <option key={d.id} value={d.id}>{d.full_name} ({d.email})</option>)}</select></div>
          <div><label htmlFor="p">Bệnh nhân</label>
            <select id="p" required value={sel.patient_id} onChange={(e) => setSel({ ...sel, patient_id: e.target.value })}>
              <option value="">– Chọn bệnh nhân –</option>{patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.email})</option>)}</select></div>
          <div style={{ alignSelf: "end" }}><button className="btn btn-primary">Phân công</button></div>
        </div>
        {doctors.length === 0 && <p className="small mut mt">Chưa có bác sĩ nào được phê duyệt. Hãy tạo hoặc phê duyệt bác sĩ ở mục Tài khoản.</p>}
      </form>

      <h2>Phân công đang hiệu lực</h2>
      {!rows ? <Loading /> : rows.length === 0 ? <Empty>Chưa có phân công nào.</Empty> : (
        <div className="card tw">
          <table>
            <thead><tr><th>Bác sĩ</th><th>Bệnh nhân</th><th>Từ ngày</th><th /></tr></thead>
            <tbody>{rows.map((a) => (
              <tr key={a.id}><td>{a.doctor.full_name}</td><td>{a.patient.full_name}</td><td>{fmtDate(a.created_at)}</td>
                <td><button className="btn btn-danger btn-sm" onClick={() => setDel(a)}>Hủy phân công</button></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {del && <ConfirmDialog title="Hủy phân công" danger confirmText="Hủy phân công" message={`Hủy phân công ${del.doctor.full_name} – ${del.patient.full_name}? Bác sĩ sẽ không còn xem được hồ sơ của bệnh nhân này.`} onConfirm={end} onCancel={() => setDel(null)} />}
    </div>
  );
}
