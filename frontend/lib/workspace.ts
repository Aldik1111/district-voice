"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Appeal } from "./api";
import { AnalysisGroup, AnalysisResult, AnalysisRun } from "./analysis";

export type Breakdown = { name: string; count: number; percent: number };
export type DashboardData = {
  total_appeals: number; unique_appeals: number | null; republications: number | null;
  analysis_total: number; analyzed: number; groups_count: number | null; pending_review: number | null;
  confirmed_groups: number; rejected_groups: number; case_count: number; problem_count: number;
  privacy_review: number; period: { start: string; end: string } | null;
  by_date: { date: string; count: number }[]; by_category: Breakdown[]; by_territory: Breakdown[];
  latest_groups: AnalysisGroup[]; latest_problems: AnalysisGroup[]; run: AnalysisRun | null;
};
export type RegistryAppeal = Appeal & {
  category: string | null; classification_method: string | null; requires_reanalysis: boolean;
  groups: { id: string; kind: "case" | "problem"; category: string; status: string }[];
};
export type RegistryPage = { items: RegistryAppeal[]; total: number; page: number; page_size: number; categories: string[]; sources: string[]; run: AnalysisRun | null };
export type ReviewEvent = { previous_status: string; status: string; reason: string; created_at: string; version: number; actor: string; action?: string; old_value?: Record<string, unknown>; new_value?: Record<string, unknown> };
export type ReviewedGroup = AnalysisGroup & { review_history?: ReviewEvent[] };
export type AnalysisReport = {
  report_type: string; approved_summary: boolean; notice: string; generated_at: string;
  summary: DashboardData; groups: ReviewedGroup[]; appeals: AnalysisResult[];
};

/** Keys prevent a response for an older URL from being shown as the current view. */
export function useResource<T>(path: string) {
  const [revision, setRevision] = useState(0);
  const key = `${path}:${revision}`;
  const [state, setState] = useState<{ key: string; data?: T; error?: string }>({ key: "" });
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal }).then(data => {
      if (live) setState({ key, data });
    }).catch(error => {
      if (live) setState({ key, error: error instanceof Error ? error.message : "Не удалось загрузить данные." });
    });
    return () => { live = false; controller.abort(); };
  }, [path, key]);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  return { data: state.key === key ? state.data : undefined, loading: state.key !== key, error: state.key === key ? state.error : undefined, reload };
}

export async function downloadReport(runId: string) {
  // Validate first so a backend failure is shown in the page. The attachment is
  // served over HTTP, including browsers that do not support blob downloads.
  await api<AnalysisReport>(`/reports/${encodeURIComponent(runId)}`);
  const link = document.createElement("a");
  link.href = `/api/reports/${encodeURIComponent(runId)}?download=true`;
  link.download = `district-voice-${runId.slice(0, 8)}.json`;
  document.body.appendChild(link); link.click(); link.remove();
}

const analysisStates: Record<string, string> = { pending: "Ожидает анализа", running: "В обработке", analyzed: "Обработано", review_required: "Нужна проверка", blocked: "Проверить данные", error: "Ошибка анализа", failed: "Ошибка анализа" };
export const analysisStateLabel = (status: string) => analysisStates[status] || status;
