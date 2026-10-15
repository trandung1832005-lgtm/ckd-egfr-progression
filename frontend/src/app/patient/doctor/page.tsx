"use client";

import { useEffect, useState } from "react";
import { Alert, Empty, Loading } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Doc { id: string; full_name: string; specialty: string | null; assigned_at: string }

export default function PatientDoctor() {
  const { user } = useAuth();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!user) return;
    api<{ doctors: Doc[] }>(`/api/patients/${user.id}/doctors`)
      .then((d) => setDocs(d.doctors))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được dữ liệu."));
  }, [user]);
  if (err) return <Alert kind="error">{err}</Alert>;
  if (!docs) return <Loading />;
  return (
    <div>
      <h1>Bác sĩ phụ trách</h1>
      <p className="mut">Bác sĩ được phân công mới xem được hồ sơ và kết quả của bạn.</p>
      {docs.length === 0 ? <Empty>Bạn chưa được phân công bác sĩ. Quản trị viên sẽ phân công cho bạn.</Empty> : (
        <div className="grid">
          {docs.map((d) => (
            <div className="card" key={d.id}>
              <h2>{d.full_name}</h2>
              <p className="mut">{d.specialty ?? "Chưa cập nhật chuyên khoa"}</p>
              <p className="small mut">Phụ trách từ {fmtDate(d.assigned_at)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
