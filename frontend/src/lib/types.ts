export type Role = "patient" | "doctor" | "admin";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  status: string;
  must_change_password: boolean;
  profile?: { birth_year?: number | null; gender_code?: number | null; specialty?: string | null; approved?: boolean };
}

export interface EgfrRecord {
  id: string;
  recorded_on: string;
  egfr: number;
  note: string | null;
  source: "patient" | "doctor";
  created_at: string;
  replaces_id: string | null;
  voided: boolean;
}

export interface Guidance {
  stage: string;
  description: string;
  goals: string[];
  dietary_focus: string[];
  lifestyle: string[];
  monitoring: string[];
  complications: string[];
}

export interface PredictionResult {
  history: Record<string, number | null>;
  forecast: { month: number; egfr: number; stage: string }[];
  final_stage: string;
  warnings: string[];
  guidance: Guidance;
  gmm: {
    cluster: number;
    name: string;
    names: string[];
    probabilities: number[];
    total_slope: number;
    history_slope: number | null;
    forecast_slope: number;
    note: string;
  };
}

export interface Prediction {
  id: string;
  patient_id: string;
  created_at: string;
  model_version: string;
  created_by: string;
  created_by_name?: string | null;
  created_by_role?: string | null;
  result: PredictionResult;
  input?: {
    id: string;
    egfr: Record<string, number | null>;
    clinical: Record<string, number>;
    created_at: string;
    replaces_id: string | null;
  };
}

export interface Note {
  id: string;
  doctor_id: string;
  doctor_name: string | null;
  body: string;
  plan: string | null;
  follow_up_on: string | null;
  prediction_id: string | null;
  created_at: string;
}

export type HistoryItem =
  | ({ type: "egfr"; at: string } & EgfrRecord)
  | ({ type: "prediction"; at: string } & Prediction)
  | ({ type: "note"; at: string } & Note);

export interface ModelSpec {
  future_months: number[];
  use_clinical: boolean;
  clinical_columns: string[];
  input_ranges: Record<string, [number, number]>;
  etiology_levels: number[];
}

export interface Suggestion {
  egfr: { "0M": number | null; "6M": number | null; "12M": number | null };
  dates: Record<string, string>;
  clinical: Record<string, number>;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  status: string;
  created_at: string | null;
  last_login_at: string | null;
  doctor?: { specialty: string | null; license_no: string | null; approved: boolean } | null;
}
