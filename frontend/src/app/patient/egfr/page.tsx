"use client";

import RecordsPanel from "@/components/RecordsPanel";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function PatientEgfr() {
  const { user } = useAuth();
  if (!user) return <Loading />;
  return (
    <div>
      <h1>Chỉ số eGFR</h1>
      <p className="mut">Các kết quả eGFR thực tế của bạn theo thời gian. Đây là số đo đã nhập, không phải dự đoán.</p>
      <div className="card"><RecordsPanel patientId={user.id} /></div>
    </div>
  );
}
