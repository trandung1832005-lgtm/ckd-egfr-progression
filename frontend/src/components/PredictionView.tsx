"use client";

import { fmtDateTime, fmtNum } from "@/lib/api";
import type { Prediction } from "@/lib/types";
import { ForecastChart } from "./charts";
import { Alert, CLINICAL_LABELS, SourceBadge, TrendBadge } from "./ui";

const PATIENT_TREND: Record<string, string> = {
  "Chuyển biến xấu": "Chức năng thận có xu hướng giảm nhanh hơn đa số bệnh nhân khác. Hãy trao đổi sớm với bác sĩ chuyên khoa thận.",
  "Ổn định": "Chức năng thận thay đổi chậm so với các nhóm khác. Hãy tiếp tục theo dõi định kỳ và duy trì điều trị.",
  "Cải thiện": "Xu hướng chức năng thận tốt hơn so với đa số bệnh nhân khác. Hãy tiếp tục duy trì điều trị và theo dõi định kỳ.",
};
const GUIDE_BLOCKS: [keyof Prediction["result"]["guidance"], string][] = [
  ["goals", "Mục tiêu chính"], ["dietary_focus", "Chế độ ăn"], ["lifestyle", "Lối sống"],
  ["monitoring", "Theo dõi"], ["complications", "Biến chứng cần lưu ý"],
];

export default function PredictionView({ pred, audience }: { pred: Prediction; audience: "patient" | "doctor" }) {
  const r = pred.result;
  const g = r.gmm;
  const last = r.forecast[r.forecast.length - 1];
  const doctor = audience === "doctor";
  return (
    <div>
      <p className="mut small">
        Dự đoán lúc {fmtDateTime(pred.created_at)}
        {doctor && pred.created_by_name && <> · thực hiện bởi {pred.created_by_name} ({pred.created_by_role === "doctor" ? "bác sĩ" : "bệnh nhân"})</>}
        {doctor && <> · mô hình {pred.model_version}</>}
      </p>
      {r.warnings.map((w, i) => <Alert key={i} kind="warn">{w}</Alert>)}

      <div className="grid">
        <div className="stat">
          <div className="l">eGFR dự đoán sau 36 tháng</div>
          <div className="v">{fmtNum(last.egfr)}</div>
          <div className="small mut">mL/phút/1,73 m² · <SourceBadge kind="pred" /></div>
        </div>
        <div className="stat">
          <div className="l">Mức tham chiếu theo eGFR dự đoán</div>
          <div className="v">{r.final_stage}</div>
          <div className="small mut">Theo ngưỡng eGFR; không phải chẩn đoán</div>
        </div>
        <div className="stat">
          <div className="l">Xu hướng chức năng thận</div>
          <div className="v" style={{ fontSize: "1.1rem" }}><TrendBadge name={g.name} /></div>
          <div className="small mut">{doctor ? "Phân nhóm thống kê (GMM)" : "So với các bệnh nhân khác"}</div>
        </div>
      </div>

      <p className="mt">{doctor ? g.note : PATIENT_TREND[g.name]}</p>

      <ForecastChart result={r} />
      <div className="tw">
        <table>
          <thead><tr><th>Mốc</th><th>Loại</th><th className="num">eGFR</th><th>Mức tham chiếu</th></tr></thead>
          <tbody>
            {Object.entries(r.history).filter(([, v]) => v !== null).map(([m, v]) => (
              <tr key={m}><td>{m.replace("M", " tháng")}</td><td><SourceBadge kind="real" /></td><td className="num">{fmtNum(v)}</td><td>–</td></tr>
            ))}
            {r.forecast.map((f) => (
              <tr key={f.month}><td>{f.month} tháng</td><td><SourceBadge kind="pred" /></td><td className="num">{fmtNum(f.egfr)}</td><td>{f.stage}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {doctor && (
        <details className="card mt">
          <summary><b>Chi tiết kỹ thuật cho bác sĩ</b></summary>
          <p className="small mt">Độ dốc toàn quỹ đạo: <b>{fmtNum(g.total_slope, 2)}</b> mL/phút/1,73 m²/năm · lịch sử đã đo: <b>{fmtNum(g.history_slope, 2)}</b> · dự báo: <b>{fmtNum(g.forecast_slope, 2)}</b></p>
          <table>
            <thead><tr><th>Nhóm</th><th className="num">Xác suất</th></tr></thead>
            <tbody>{g.names.map((n, i) => <tr key={n}><td>{n}{i + 1 === g.cluster ? " ✓" : ""}</td><td className="num">{fmtNum(g.probabilities[i] * 100)}%</td></tr>)}</tbody>
          </table>
          <p className="small mut mt">Nhóm là nhãn tương đối theo thứ hạng độ dốc trong mẫu huấn luyện, không phải giai đoạn bệnh. Nhóm “Ổn định” trong mẫu này vẫn có độ dốc âm.</p>
          {pred.input && (
            <>
              <h3>Dữ liệu đầu vào đã dùng</h3>
              <p className="small">eGFR 0/6/12 tháng: {["0M", "6M", "12M"].map((k) => fmtNum(pred.input!.egfr[k])).join(" / ")}</p>
              <div className="tw"><table><tbody>
                {Object.entries(pred.input.clinical).map(([k, v]) => <tr key={k}><td>{CLINICAL_LABELS[k] ?? k}</td><td className="num">{v}</td></tr>)}
              </tbody></table></div>
            </>
          )}
        </details>
      )}

      <details className="card mt" open={!doctor}>
        <summary><b>Hướng dẫn chăm sóc tham khảo – {r.guidance.stage}</b></summary>
        <p className="mt">{r.guidance.description}</p>
        {GUIDE_BLOCKS.map(([k, label]) => (
          <div key={k}>
            <h3>{label}</h3>
            <ul className="plain">{(r.guidance[k] as string[]).map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        ))}
        <p className="small mut">Áp dụng cho mức eGFR <b>dự đoán</b> sau 36 tháng, chỉ mang tính tham khảo, không thay thế tư vấn của bác sĩ chuyên khoa thận.</p>
      </details>
    </div>
  );
}
