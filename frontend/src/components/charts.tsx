"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EgfrRecord, PredictionResult } from "@/lib/types";

const TEAL = "#0a6f6a";
const ORANGE = "#d46a0f";
// Trục eGFR co theo dữ liệu (không ép từ 0) để thấy rõ biến động, nhưng không âm.
const yDomain: [(min: number) => number, (max: number) => number] = [(m) => Math.max(0, Math.floor(m - 5)), (M) => Math.ceil(M + 5)];

/** eGFR thực tế theo ngày đo. */
export function RecordsChart({ records }: { records: EgfrRecord[] }) {
  const data = [...records]
    .sort((a, b) => a.recorded_on.localeCompare(b.recorded_on))
    .map((r) => ({ t: new Date(r.recorded_on).getTime(), egfr: r.egfr }));
  if (data.length === 0) return null;
  return (
    <div style={{ height: 280 }} role="img" aria-label="Biểu đồ eGFR đã đo theo thời gian">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#e3e9ee" />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]}
                 tickFormatter={(t: number) => new Date(t).toLocaleDateString("vi-VN", { month: "2-digit", year: "2-digit" })} />
          <YAxis domain={yDomain} label={{ value: "eGFR", angle: -90, position: "insideLeft" }} />
          <Tooltip labelFormatter={(t) => new Date(Number(t)).toLocaleDateString("vi-VN")}
                   formatter={(v) => [Number(v).toFixed(1), "eGFR đã đo"]} />
          <Line type="monotone" dataKey="egfr" stroke={TEAL} strokeWidth={2.5} dot={{ r: 4 }} name="Đã đo" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Lịch sử đã nhập (đường liền) và dự đoán (đường đứt) theo mốc tháng. */
export function ForecastChart({ result }: { result: PredictionResult }) {
  const hist = Object.entries(result.history)
    .filter(([, v]) => v !== null)
    .map(([m, v]) => ({ month: parseInt(m), actual: v as number }));
  const lastHist = hist[hist.length - 1];
  const rows: Record<number, { month: number; actual?: number; predicted?: number }> = {};
  hist.forEach((h) => (rows[h.month] = { month: h.month, actual: h.actual }));
  if (lastHist) rows[lastHist.month] = { ...rows[lastHist.month], predicted: lastHist.actual };   // nối đường đứt từ điểm đo cuối
  result.forecast.forEach((f) => (rows[f.month] = { month: f.month, predicted: f.egfr }));
  const data = Object.values(rows).sort((a, b) => a.month - b.month);
  return (
    <div style={{ height: 300 }} role="img" aria-label="Biểu đồ eGFR đã đo và dự đoán">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#e3e9ee" />
          <XAxis dataKey="month" type="number" domain={[0, 36]} ticks={[0, 6, 12, 18, 24, 30, 36]} height={52}
                 label={{ value: "Tháng", position: "insideBottom", offset: 0 }} />
          <YAxis domain={yDomain} label={{ value: "eGFR", angle: -90, position: "insideLeft" }} />
          <Tooltip formatter={(v, name) => [Number(v).toFixed(1), String(name)]} labelFormatter={(m) => `Tháng ${m}`} />
          <Legend verticalAlign="top" height={28} />
          <Line type="monotone" dataKey="actual" name="Đã đo" stroke={TEAL} strokeWidth={2.5} dot={{ r: 4 }} connectNulls isAnimationActive={false} />
          <Line type="monotone" dataKey="predicted" name="Dự đoán" stroke={ORANGE} strokeWidth={2.5} strokeDasharray="6 5"
                dot={{ r: 4 }} connectNulls isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
