"use client";

import { useEffect, useState } from "react";
import { Alert, Empty, Loading } from "@/components/ui";
import { api, ApiError, fmtDateTime } from "@/lib/api";

interface Log {
  id: number; at: string; actor_name: string | null; actor_role: string | null; action: string;
  target_type: string | null; target_id: string | null; ip: string | null; detail: string | null;
}
const PAGE = 50;
const ACTIONS: [string, string][] = [
  ["", "Tất cả"], ["auth.login", "Đăng nhập thành công"], ["auth.login_failed", "Đăng nhập thất bại"], ["auth.lockout", "Khóa tạm do đăng nhập sai"],
  ["auth.logout", "Đăng xuất"], ["auth.password_changed", "Đổi mật khẩu"], ["auth.password_reset", "Đặt lại mật khẩu"],
  ["admin.user_create", "Tạo tài khoản"], ["admin.user_lock", "Khóa tài khoản"], ["admin.user_unlock", "Mở khóa tài khoản"],
  ["admin.doctor_approve", "Phê duyệt bác sĩ"], ["admin.doctor_revoke", "Thu hồi phê duyệt"], ["admin.assign", "Phân công"], ["admin.unassign", "Hủy phân công"],
  ["patient.view", "Bác sĩ mở hồ sơ bệnh nhân"], ["prediction.create", "Tạo dự đoán"], ["prediction.view", "Bác sĩ xem dự đoán"],
];
const label = (a: string) => ACTIONS.find(([k]) => k === a)?.[1] ?? a;

export default function AdminAudit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<{ total: number; logs: Log[] } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    if (action) p.set("action", action);
    api<{ total: number; logs: Log[] }>(`/api/admin/audit-logs?${p}`)
      .then((d) => { if (alive) { setData(d); setErr(""); } })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "Không tải được nhật ký."); });
    return () => { alive = false; };
  }, [action, page]);

  return (
    <div>
      <h1>Nhật ký hoạt động</h1>
      <p className="mut">Các thao tác đăng nhập, phân quyền và truy cập hồ sơ. Nhật ký không chứa mật khẩu hay số liệu y tế.</p>
      <div className="card">
        <label htmlFor="a">Loại hoạt động</label>
        <select id="a" value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }}>{ACTIONS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>
      </div>
      {err && <Alert kind="error">{err}</Alert>}
      {!data && !err && <Loading />}
      {data && data.logs.length === 0 && <Empty>Không có hoạt động nào.</Empty>}
      {data && data.logs.length > 0 && (
        <div className="card tw">
          <table>
            <thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Hoạt động</th><th>Đối tượng</th><th>IP</th></tr></thead>
            <tbody>{data.logs.map((l) => (
              <tr key={l.id}>
                <td className="small">{fmtDateTime(l.at)}</td>
                <td>{l.actor_name ?? <span className="mut">(không xác định)</span>}{l.actor_role && <div className="small mut">{l.actor_role}</div>}</td>
                <td>{label(l.action)}<div className="small mut">{l.action}</div></td>
                <td className="small">{l.target_type ?? "–"}{l.detail && <div className="mut" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }} title={l.detail}>{l.detail}</div>}</td>
                <td className="small">{l.ip ?? "–"}</td>
              </tr>
            ))}</tbody>
          </table>
          <div className="row mt">
            <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>← Trước</button>
            <span className="small mut">Trang {page + 1} / {Math.max(1, Math.ceil(data.total / PAGE))} · {data.total} bản ghi</span>
            <button className="btn btn-sm" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Sau →</button>
          </div>
        </div>
      )}
    </div>
  );
}
