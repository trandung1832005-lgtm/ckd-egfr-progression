"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ModelSpec, Prediction, Suggestion } from "@/lib/types";
import { Alert, BINARY_FIELDS, CLINICAL_LABELS, Loading } from "./ui";

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function PredictionForm({ patientId, onCreated }: { patientId: string; onCreated: (p: Prediction) => void }) {
  const [spec, setSpec] = useState<ModelSpec | null>(null);
  const [sug, setSug] = useState<Suggestion | null>(null);
  const [egfr, setEgfr] = useState({ "0M": "", "6M": "", "12M": "" });
  const [clin, setClin] = useState<Record<string, string>>({});
  const [loadErr, setLoadErr] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [s, g] = await Promise.all([
          api<ModelSpec>("/api/models/spec"),
          api<Suggestion>(`/api/patients/${patientId}/inputs/suggest`),
        ]);
        if (!alive) return;
        setSpec(s);
        setSug(g);
        setEgfr({ "0M": g.egfr["0M"]?.toString() ?? "", "6M": g.egfr["6M"]?.toString() ?? "", "12M": g.egfr["12M"]?.toString() ?? "" });
        setClin(Object.fromEntries(Object.entries(g.clinical).map(([k, v]) => [k, String(v)])));
      } catch (e) {
        if (alive) setLoadErr(e instanceof ApiError ? e.message : "Không tải được biểu mẫu.");
      }
    })();
    return () => { alive = false; };
  }, [patientId]);

  if (loadErr) return <Alert kind="error">{loadErr}</Alert>;
  if (!spec || !sug) return <Loading />;

  const hasSuggestion = sug.egfr["0M"] !== null;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const num = (s: string) => (s.trim() === "" ? null : Number(s));
      const body = {
        egfr: Object.fromEntries(Object.entries(egfr).map(([k, v]) => [k, num(v)]).filter(([k, v]) => k === "0M" || v !== null)),
        clinical: Object.fromEntries(spec.clinical_columns.map((c) => [c, Number(clin[c])])),
      };
      onCreated(await api<Prediction>(`/api/patients/${patientId}/predictions`, { body }));
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không thực hiện được dự đoán.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      {hasSuggestion
        ? <Alert kind="info">Đã điền sẵn từ các lần đo eGFR đã ghi nhận
            {Object.entries(sug.dates).map(([k, d]) => ` · ${k.replace("M", " tháng")}: ${new Date(d).toLocaleDateString("vi-VN")}`)}. Bạn có thể chỉnh trước khi gửi.</Alert>
        : <Alert kind="info">Chưa có đủ lần đo trong hồ sơ. Hãy nhập eGFR bên dưới (hoặc thêm kết quả đo ở mục “Chỉ số eGFR” để điền sẵn lần sau).</Alert>}
      <h3>Kết quả eGFR đã đo (mL/phút/1,73 m²)</h3>
      <p className="small mut">Cần ít nhất eGFR lúc bắt đầu. Nếu chưa đo ở mốc 6 hoặc 12 tháng, hãy để trống; không điền số ước đoán.</p>
      <div className="grid">
        {(["0M", "6M", "12M"] as const).map((m) => (
          <div key={m}>
            <label htmlFor={`e${m}`}>eGFR {m.replace("M", " tháng")} {m === "0M" ? "(bắt buộc)" : "(nếu đã đo)"}</label>
            <input id={`e${m}`} type="number" step="any" min="0.1" max="200" required={m === "0M"} value={egfr[m]}
                   onChange={(e) => setEgfr({ ...egfr, [m]: e.target.value })}
                   placeholder={`thường ${spec.input_ranges[`eGFR(${m})`]?.map((x) => x.toFixed(0)).join("–")}`} />
          </div>
        ))}
      </div>
      {spec.use_clinical && (
        <>
          <h3>Thông tin lâm sàng ban đầu</h3>
          <div className="grid">
            {spec.clinical_columns.map((c) => {
              const [lo, hi] = spec.input_ranges[c];
              const label = CLINICAL_LABELS[c] ?? c;
              if (BINARY_FIELDS.includes(c) || c === "etiology of CKD" || c === "CKD_stage") {
                const opts: [string, string][] = c === "etiology of CKD"
                  ? spec.etiology_levels.map((v) => [String(v), `Mã ${v}`])
                  : c === "CKD_stage"
                    ? Array.from({ length: Math.round(hi) - Math.round(lo) + 1 }, (_, i) => [String(Math.round(lo) + i), `Giai đoạn ${Math.round(lo) + i}`] as [string, string])
                    : c === "gender" ? [["1", "Mã 1"], ["2", "Mã 2"]] : [["0", "Không"], ["1", "Có"]];
                return (
                  <div key={c}>
                    <label htmlFor={c}>{label}</label>
                    <select id={c} required value={clin[c] ?? ""} onChange={(e) => setClin({ ...clin, [c]: e.target.value })}>
                      <option value="">–</option>
                      {opts.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                  </div>
                );
              }
              return (
                <div key={c}>
                  <label htmlFor={c}>{label}</label>
                  <input id={c} type="number" step="any" min="0" required value={clin[c] ?? ""}
                         onChange={(e) => setClin({ ...clin, [c]: e.target.value })} placeholder={`thường ${lo.toFixed(1)}–${hi.toFixed(1)}`} />
                </div>
              );
            })}
          </div>
        </>
      )}
      {err && <Alert kind="error">{err}</Alert>}
      <p className="mt"><button className="btn btn-primary" disabled={busy}>{busy ? "Đang xử lý…" : "Xem dự đoán"}</button></p>
      <p className="small mut">Ngày hôm nay: {new Date(todayIso()).toLocaleDateString("vi-VN")}. Kết quả được lưu vào lịch sử của hồ sơ.</p>
    </form>
  );
}
