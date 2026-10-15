"use client";

import { useState } from "react";
import PredictionForm from "@/components/PredictionForm";
import PredictionView from "@/components/PredictionView";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { Prediction } from "@/lib/types";

export default function PatientPredict() {
  const { user } = useAuth();
  const [result, setResult] = useState<Prediction | null>(null);
  if (!user) return <Loading />;
  return (
    <div>
      <h1>Dự đoán eGFR</h1>
      <p className="mut">Xem eGFR dự kiến sau 18, 24, 30 và 36 tháng dựa trên kết quả đã đo và thông tin lâm sàng. Đây là ước tính, không phải kết quả xét nghiệm.</p>
      {result ? (
        <div className="card">
          <h2>Kết quả dự đoán</h2>
          <PredictionView pred={result} audience="patient" />
          <p className="mt row">
            <button className="btn" onClick={() => setResult(null)}>Dự đoán lại với dữ liệu khác</button>
          </p>
        </div>
      ) : (
        <div className="card"><PredictionForm patientId={user.id} onCreated={setResult} /></div>
      )}
    </div>
  );
}
