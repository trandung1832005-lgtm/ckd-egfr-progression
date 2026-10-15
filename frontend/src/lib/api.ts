export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Opts = { method?: string; body?: unknown; form?: FormData };

function messageFrom(data: unknown, status: number): string {
  const d = (data as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    // Lỗi kiểm tra dữ liệu của pydantic: dịch sang thông báo tiếng Việt dễ hiểu
    const first = d[0] as { msg?: string; type?: string; loc?: (string | number)[] };
    const field = String(first.loc?.[first.loc.length - 1] ?? "");
    const msg = first.msg ?? "";
    if (field.toLowerCase().includes("email")) return "Địa chỉ email không hợp lệ.";
    if (first.type === "missing") return "Vui lòng nhập đầy đủ thông tin bắt buộc.";
    if (first.type === "value_error" && msg.startsWith("Value error, ")) return msg.slice("Value error, ".length);
    if (/greater_than|less_than|too_short|too_long|int_parsing|float_parsing|literal_error/.test(first.type ?? ""))
      return "Một số giá trị không hợp lệ hoặc nằm ngoài phạm vi cho phép. Vui lòng kiểm tra lại.";
    return "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.";
  }
  if (status === 401) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
  if (status === 403) return "Bạn không có quyền thực hiện thao tác này.";
  if (status === 404) return "Không tìm thấy dữ liệu.";
  if (status === 429) return "Thao tác quá nhanh. Vui lòng thử lại sau ít phút.";
  if (status >= 500) return "Lỗi hệ thống. Vui lòng thử lại sau.";
  return "Yêu cầu không thành công.";
}

/** Gọi API cùng domain (`/api/...`, được Next chuyển tiếp sang backend). Ném ApiError với thông điệp tiếng Việt. */
export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? (opts.body || opts.form ? "POST" : "GET"),
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      body: opts.form ?? (opts.body ? JSON.stringify(opts.body) : undefined),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Không kết nối được máy chủ. Vui lòng kiểm tra mạng và thử lại.");
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* phản hồi không phải JSON */
  }
  if (!res.ok) throw new ApiError(res.status, messageFrom(data, res.status));
  return data as T;
}

export const fmtDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("vi-VN") : "–";
export const fmtDateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }) : "–";
export const fmtNum = (x: number | null | undefined, d = 1) =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : x.toFixed(d);
