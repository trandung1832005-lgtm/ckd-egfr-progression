"use client";

import HistoryList from "@/components/HistoryList";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function PatientHistory() {
  const { user } = useAuth();
  if (!user) return <Loading />;
  return (
    <div>
      <h1>Lịch sử</h1>
      <p className="mut">Các lần ghi nhận eGFR và các lần dự đoán, mới nhất ở trên cùng.</p>
      <div className="card"><HistoryList patientId={user.id} audience="patient" /></div>
    </div>
  );
}
