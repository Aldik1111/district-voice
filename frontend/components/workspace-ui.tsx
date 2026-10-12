"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarDays, CheckCircle2, CircleHelp, GitBranch, Layers3, LoaderCircle, MapPin, Play, Radio, RefreshCw, ShieldCheck, Waves } from "lucide-react";
import { api, date, number, shortId } from "@/lib/api";
import { AnalysisGroup, AnalysisRun, algorithmLabel, groupStatusLabel } from "@/lib/analysis";

export function CategoryBadge({ category }: { category: string | null | undefined }) {
  return <span className="category-badge"><span />{category || "Не определена"}</span>;
}

export function ReviewBadge({ status }: { status: string }) {
  return <span className={`badge ${status === "confirmed" ? "badge-green" : status === "rejected" ? "badge-red" : "badge-amber"}`}>
    {status === "confirmed" ? <CheckCircle2 size={12} /> : <CircleHelp size={12} />}{groupStatusLabel(status)}
  </span>;
}

export function RunScope({ run }: { run: AnalysisRun | null | undefined }) {
  if (!run) return <div className="scope-strip"><Layers3 size={17} /><p>Категории и группы появятся после первого анализа.</p><Link href="/analysis">Запустить <ArrowRight size={14} /></Link></div>;
  return <div className={`scope-strip ${run.stale ? "scope-stale" : ""}`}>
    {run.stale ? <RefreshCw size={17} /> : <ShieldCheck size={17} />}
    <p>{run.stale ? "Данные изменились. Показан сохранённый анализ — требуется пересчёт." : <>По анализу от {date(run.finished_at)} · {algorithmLabel(run.algorithm)}</>}</p>
    <Link href="/analysis">{run.stale ? "Пересчитать" : "К анализу"}<ArrowRight size={14} /></Link>
  </div>;
}

export function RunButton({ completed, disabled = false }: { completed?: () => void; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await api<AnalysisRun>("/analysis/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "auto" }) });
      if (result.status !== "completed") throw new Error("Анализ не завершён. Подробности доступны в разделе AI-анализ.");
      completed?.();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Ошибка анализа."); }
    finally { setBusy(false); }
  }
  return <div className="run-control"><button className="button button-primary" onClick={run} disabled={busy || disabled}>{busy ? <LoaderCircle size={17} className="spin" /> : <Play size={16} />}{busy ? "Анализ выполняется…" : "Запустить анализ"}</button>{busy && <span role="status">Локальная обработка · без оценки процента</span>}{error && <span className="run-error" role="alert">{error}</span>}</div>;
}

export function GroupCard({ group }: { group: AnalysisGroup }) {
  return <article className="problem-card">
    <div className="problem-card-top"><span className="category-icon">{group.kind === "problem" ? <GitBranch size={22} /> : <Waves size={22} />}</span><ReviewBadge status={group.status} /></div>
    <div className="problem-kind">{group.kind === "problem" ? "Повторяющаяся проблема" : "Локальный случай"} <span>#{shortId(group.id)}</span></div>
    <h3><Link href={`/problems/${group.id}`}>{group.title || group.category}</Link></h3>
    <p className="problem-territory"><MapPin size={15} />{group.territory || "Территория неизвестна"}</p>
    <p className="problem-period"><CalendarDays size={14} />{date(group.start_date)} — {date(group.end_date)}</p>
    <div className="problem-card-counts"><div><strong>{number(group.message_count)}</strong><span>обращений</span></div><div><strong>{number(group.source_count)}</strong><span>источников</span></div><div><strong>{number(group.independent_evidence_count)}</strong><span>без копий*</span></div></div>
    <div className="problem-card-bottom"><span><Radio size={13} />{group.uncertainties.length ? "Есть замечания" : "Проверить основания"}</span><Link href={`/problems/${group.id}`}>Подробнее <ArrowRight size={15} /></Link></div>
  </article>;
}
