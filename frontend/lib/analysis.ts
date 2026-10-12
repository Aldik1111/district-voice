import type { Appeal, PrivacyStatus } from "./api";

export type Algorithm = {
  name: string;
  label: string;
  semantic: boolean;
  model_id?: string | null;
  fallback_reason?: string | null;
  model_load_verified?: boolean;
  available?: boolean;
};
export type AnalysisRun = {
  id: string;
  status: string;
  algorithm: Algorithm | string;
  created_at: string;
  finished_at?: string | null;
  total: number;
  analyzed: number;
  blocked: number;
  error_count: number;
  errors: (string | { message?: string; error?: string; appeal_id?: string })[];
  uncertainties_count: number;
  case_count: number;
  problem_count: number;
  stale: boolean;
  rerun_of?: string | null;
};
export type AnalysisStatus = {
  algorithm: Algorithm;
  latest_run: AnalysisRun | null;
  categories: string[];
  total_appeals: number;
  pending_appeals: number;
};
export type AnalysisResult = {
  id: string;
  version: number;
  appeal_id: string;
  source_record_id: string;
  source?: string;
  text: string;
  date: string;
  address: string;
  privacy_status?: PrivacyStatus;
  category: string;
  proposed_category: string;
  classification_method: string;
  score: number | null;
  uncertainties: string[];
  territory: string | null;
  duplicate_kind: "independent" | "republication_candidate";
  duplicate_of?: string | null;
  explanations: string[];
  status: "analyzed" | "review_required" | "blocked";
  input_version: number;
  override_category?: string | null;
  requires_reanalysis?: boolean;
};
export type AnalysisGroup = {
  id: string;
  run_id: string;
  kind: "case" | "problem";
  version: number;
  status: string;
  category: string;
  territory: string | null;
  title?: string;
  explanation_stale?: boolean;
  merged_into?: string;
  start_date: string;
  end_date: string;
  appeal_ids: string[];
  message_count: number;
  source_count: number;
  independent_evidence_count: number;
  explanations: string[];
  uncertainties: string[];
  minimum_similarity: number | null;
  case_ids?: string[];
  stale?: boolean;
};
export type GroupEvidence = Appeal & { appeal_version?: number; analysis: AnalysisResult | null };
export type AnalysisIssue = { appeal_id?: string; kind: string; message: string };

export const scoreLabel = (score: number | null | undefined) => typeof score === "number" && Number.isFinite(score) ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3, minimumFractionDigits: 2 }).format(score) : "—";
export const algorithmLabel = (algorithm?: Algorithm | string | null) => {
  if (!algorithm) return "Метод не указан";
  if (typeof algorithm !== "string") {
    if (algorithm.name === "pending") return algorithm.label || "Алгоритм ещё не определён";
    if (algorithm.semantic) return algorithm.label || "Мультиязычный E5";
    return /tf.?idf/i.test(algorithm.name) ? "TF-IDF (резервный текстовый метод)" : algorithm.label || algorithm.name;
  }
  return /tf.?idf/i.test(algorithm) ? "TF-IDF (резервный текстовый метод)" : /e5|semantic|sentence/i.test(algorithm) ? "Мультиязычный E5" : algorithm;
};
export const availableAlgorithmLabel = (algorithm: Algorithm) => algorithm.semantic && algorithm.model_load_verified !== true ? "E5 найден локально · загрузка не проверена" : algorithmLabel(algorithm);
export const runStatusLabel = (status: string) => (({ completed: "Завершён", completed_with_errors: "Завершён с замечаниями", running: "Выполняется", failed: "Ошибка анализа", partial: "Частичный результат", succeeded: "Завершён" } as Record<string, string>)[status] || status);
export const methodLabel = (method: string) => (({ manual: "Ручная категория", manual_override: "Ручная категория", bilingual_rules: "Двуязычные словарные правила", "e5_prototypes+bilingual_rules": "Прототипы E5 и двуязычные правила", rules: "Словарные правила", keyword: "Словарные правила", tfidf: "Текстовое сходство TF-IDF", semantic: "Семантическое сходство E5", blocked: "Анализ заблокирован", blocked_privacy: "Заблокировано: проверка личных сведений", fallback: "Резервный текстовый метод" } as Record<string, string>)[method] || method);
export const resultStatusLabel = (status: string) => (({ analyzed: "Обработано", review_required: "Нужна оценка аналитика", blocked: "Проверить обезличивание" } as Record<string, string>)[status] || status);
export const groupStatusLabel = (status: string) => (({ archived: "Объединена · архив", proposed: "Предложена системой", suggested: "Предложена системой", confirmed: "Подтверждена", rejected: "Отклонена", review_required: "Нужна проверка", stale: "Требует пересчёта" } as Record<string, string>)[status] || status);
export const issueLabel = (kind: string) => (({ privacy: "Обезличивание", uncertainty: "Неопределённость", analysis_error: "Ошибка", stale_snapshot: "Устаревший снимок", stale: "Нужен пересчёт", interrupted: "Запуск прерван" } as Record<string, string>)[kind] || "Замечание");
