"use client";

import { useEffect, useRef } from "react";

export function Alert({ kind = "info", children }: { kind?: "error" | "ok" | "warn" | "info"; children: React.ReactNode }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export const Loading = ({ text = "Đang tải…" }: { text?: string }) => <div className="loading" aria-live="polite">{text}</div>;
export const Empty = ({ children }: { children: React.ReactNode }) => <div className="empty">{children}</div>;

export const trendClass = (name: string) =>
  name === "Chuyển biến xấu" ? "b-bad" : name === "Cải thiện" ? "b-ok" : "b-mid";

export function TrendBadge({ name }: { name: string }) {
  return <span className={`badge ${trendClass(name)}`}>{name}</span>;
}

export const SourceBadge = ({ kind }: { kind: "real" | "pred" }) => (
  <span className={`badge ${kind === "real" ? "b-real" : "b-pred"}`}>{kind === "real" ? "Đã đo" : "Dự đoán"}</span>
);

/** Hộp xác nhận cho thao tác quan trọng (khóa tài khoản, hủy phân công…). */
export function ConfirmDialog({
  title, message, confirmText = "Xác nhận", danger = false, onConfirm, onCancel,
}: {
  title: string; message: string; confirmText?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="modal-back" onClick={onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <p>{message}</p>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={onCancel}>Hủy</button>
          <button ref={ref} className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm}>{confirmText}</button>
        </div>
      </div>
    </div>
  );
}

export const GENDER_LABEL: Record<number, string> = { 1: "Mã 1", 2: "Mã 2" };

export const CLINICAL_LABELS: Record<string, string> = {
  gender: "Giới tính (mã 1/2 theo dữ liệu)", age: "Tuổi", hypertension: "Tăng huyết áp", "prevalence of CVD": "Bệnh tim mạch",
  diabetes: "Đái tháo đường", "use of RAASi": "Dùng thuốc ức chế RAAS", "use of CCB": "Dùng thuốc chẹn kênh canxi",
  "use of diuretics": "Dùng thuốc lợi tiểu", "etiology of CKD": "Nguyên nhân bệnh thận (mã)", SBP: "Huyết áp tâm thu (mmHg)",
  BMI: "BMI (kg/m²)", Hb: "Hemoglobin (g/dL)", Alb: "Albumin (g/dL)", Cr: "Creatinine (mg/dL)", UPCR: "UPCR (g/gCr)",
  proteinuria: "Protein niệu", CKD_stage: "Giai đoạn CKD hiện tại",
};
export const BINARY_FIELDS = ["gender", "hypertension", "prevalence of CVD", "diabetes", "use of RAASi", "use of CCB", "use of diuretics", "proteinuria"];
