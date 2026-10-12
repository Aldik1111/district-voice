"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Download, FileBarChart2, FileJson, LoaderCircle, Printer, RefreshCw } from "lucide-react";
import { date, number, shortId } from "@/lib/api";
import { AnalysisRun, algorithmLabel, runStatusLabel } from "@/lib/analysis";
import { AnalysisReport, downloadReport, useResource } from "@/lib/workspace";
import { Empty, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { ReviewBadge } from "@/components/workspace-ui";

function ReportPreview({ runId }: { runId: string }) {
  const { data: report, loading, error, reload } = useResource<AnalysisReport>(`/reports/${runId}`);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [saved, setSaved] = useState(false);
  async function download() {
    setExporting(true); setExportError(""); setSaved(false);
    try { await downloadReport(runId); setSaved(true); }
    catch (cause) { setExportError(cause instanceof Error ? cause.message : "Ошибка экспорта."); }
    finally { setExporting(false); }
  }
  if (loading) return <Loading label="Собираем сохранённый снимок анализа…" />;
  if (error) return <ErrorBox message={error} retry={reload} />;
  if (!report) return null;
  const summary = report.summary;
  return <>
    <div className="report-actions"><p><FileJson size={17} />Состав групп, показатели и подтверждающие ID</p><button className="button button-white" onClick={() => window.print()}><Printer size={16} />Печать</button><button className="button button-primary" disabled={exporting} onClick={download}>{exporting ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}Скачать JSON</button></div>
    {exportError && <ErrorBox message={exportError} />}{saved && <div className="success-notice" role="status"><CheckCircle2 size={17} />Файл сформирован и передан браузеру для сохранения.</div>}
    <article className="panel report-document"><div className="report-document-heading"><span className="report-document-icon"><FileBarChart2 size={28} /></span><div><p className="section-kicker">ГОЛОС РАЙОНА · АНАЛИТИЧЕСКИЙ СНИМОК</p><h2>Обращения и найденные связи</h2><p>{date(summary.run?.finished_at)} · запуск #{shortId(runId)}</p></div><span className="badge badge-amber">Рабочий отчёт</span></div>
      <div className="report-disclaimer"><strong>Для проверки аналитиком</strong><p>{report.notice}</p>{summary.run?.stale && <p>Исходные данные изменились после запуска. Ниже сохранённые результаты, требующие повторного анализа.</p>}</div>
      <div className="report-metrics"><div><span>Обращений в запуске</span><strong>{number(summary.total_appeals)}</strong></div><div><span>Локальных случаев</span><strong>{number(summary.case_count)}</strong></div><div><span>Повторяющихся проблем</span><strong>{number(summary.problem_count)}</strong></div><div><span>Групп подтверждено</span><strong>{number(summary.confirmed_groups)}</strong></div></div>
      <div className="report-method"><span>Метод</span><strong>{algorithmLabel(summary.run?.algorithm)}</strong><span>Период обращений</span><strong>{summary.period ? `${date(summary.period.start)} — ${date(summary.period.end)}` : "Не определён"}</strong></div>
      <div className="report-section"><h3>Распределение по категориям</h3>{summary.by_category.length ? <div className="report-categories">{summary.by_category.map(item => <div key={item.name}><span>{item.name}</span><strong>{number(item.count)}</strong></div>)}</div> : <p>Допущенных к классификации обращений нет.</p>}</div>
      <div className="report-section"><h3>Группы и статус проверки</h3><div className="table-scroll"><table className="data-table"><thead><tr><th>Группа</th><th>Территория / период</th><th>Обращения / источники</th><th>Проверка</th></tr></thead><tbody>{report.groups.map(group => <tr key={group.id}><td><Link className="table-title-link" href={`/problems/${group.id}`}>{group.category}</Link><small>{group.kind === "case" ? "Локальный случай" : "Повторяющаяся проблема"} · #{shortId(group.id)}</small></td><td>{group.territory || "Территория неизвестна"}<small>{date(group.start_date)} — {date(group.end_date)}</small></td><td>{number(group.message_count)} / {number(group.source_count)}</td><td><ReviewBadge status={group.status} /></td></tr>)}</tbody></table>{!report.groups.length && <p className="table-empty">Групп в этом запуске нет.</p>}</div></div>
      <p className="report-footer">Числа рассчитаны локально по SQLite. JSON включает реальные ID и обезличенные снимки обращений. Сходство и количество сообщений не доказывают общую причину события или независимость авторов.</p>
    </article>
  </>;
}

export default function LegacyReports() {
  const { data: runs, loading, error, reload } = useResource<AnalysisRun[]>("/analysis/runs");
  const [selected, setSelected] = useState("");
  const completed = (runs || []).filter(run => run.status === "completed");
  const runId = selected || completed[0]?.id;
  return <><PageTitle eyebrow="ПРОВЕРЯЕМЫЕ РЕЗУЛЬТАТЫ" title="Снимки анализа" description="Сохранённые результаты анализа для обсуждения, сверки и демонстрации."><button className="button button-white" disabled={loading} onClick={reload}><RefreshCw size={16} />Обновить</button></PageTitle>
    {error ? <ErrorBox message={error} retry={reload} /> : loading ? <Loading /> : !completed.length ? <section className="panel"><Empty title="Пока нет готового анализа" description="Завершите первый запуск. Здесь появятся его проверяемые показатели, группы и экспорт JSON." action={<Link className="button button-primary" href="/analysis">Перейти к анализу <ArrowRight size={15} /></Link>} /></section> : <><div className="report-run-picker"><label className="field"><span>Сохранённый запуск</span><select value={runId} onChange={event => setSelected(event.target.value)}>{completed.map(run => <option value={run.id} key={run.id}>{date(run.finished_at)} · #{shortId(run.id)} · {algorithmLabel(run.algorithm)}</option>)}</select></label><span className="badge badge-green">{runStatusLabel("completed")}</span></div>{runId && <ReportPreview key={runId} runId={runId} />}</>}
  </>;
}
