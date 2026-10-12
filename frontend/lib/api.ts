export type PrivacyStatus = "clear" | "masked" | "review_required";
export type Appeal = {
  id: string;
  version: number;
  source: string;
  source_record_id: string;
  date: string;
  text: string;
  address: string;
  official_status: string;
  language: string;
  privacy_status: PrivacyStatus;
  warnings: string[];
  analysis_status: string;
  created_at: string;
};
export type PreviewRow = Omit<Appeal, "id" | "version" | "created_at" | "analysis_status"> & {
  row_number: number;
  errors: string[];
  duplicate_status: "new" | "duplicate" | "conflict";
};
export type Preview = {
  preview_id: string;
  filename: string;
  columns: string[];
  mapping: Record<string, string>;
  rows: PreviewRow[];
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  conflict_rows: number;
};
export type ImportResult = { batch_id: string; accepted: number; rejected: number; duplicates: number; conflicts: number };
export type Batch = Omit<ImportResult, "batch_id"> & { id: string; filename: string; created_at: string };
export type Stats = {
  total_appeals: number;
  total_batches: number;
  review_required: number;
  masked: number;
  by_source: { name: string; count: number }[];
  by_date: { date: string; count: number }[];
  by_territory: { name: string; count: number }[];
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new Error("Не удалось подключиться к серверу. Проверьте, что backend запущен.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg || "Ошибка проверки данных").join("; ") : body?.message;
    throw new ApiError(message || `Сервер вернул ошибку ${response.status}. Попробуйте ещё раз.`, response.status);
  }
  return response.json() as Promise<T>;
}

export const number = (value: number) => new Intl.NumberFormat("ru-RU").format(value);
export const shortId = (value: string) => value.slice(0, 8);
export const date = (value: string | null | undefined) => {
  if (!value) return "—";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
};
export const privacyLabels: Record<string, string> = { clear: "Признаков не найдено", masked: "Данные скрыты", review_required: "Нужна проверка" };
