"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, BookOpen, CalendarDays, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, FileText, GitBranch, History, Layers3, ListFilter, LoaderCircle, MapPin, PencilLine, Play, RefreshCw, Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { api, ApiError, date, number, shortId } from "@/lib/api";
import { AnalysisGroup, AnalysisIssue, AnalysisResult, AnalysisRun, AnalysisStatus, GroupEvidence, algorithmLabel, availableAlgorithmLabel, groupStatusLabel, issueLabel, methodLabel, resultStatusLabel, runStatusLabel, scoreLabel } from "@/lib/analysis";
import { Empty, ErrorBox, ImportLink, Loading, PageTitle, PrivacyBadge } from "@/components/ui";

type Tab = "results" | "cases" | "problems";
type Mode = "auto" | "tfidf";

function Notes({ items, warning = false }: { items: string[]; warning?: boolean }) {
  if (!items.length) return null;
  return <div className={`analysis-notes ${warning ? "analysis-notes-warning" : ""}`}><h3>{warning ? <AlertTriangle size={14} /> : <BookOpen size={14} />}{warning ? "Неопределённости" : "Основания решения"}</h3><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>;
}

function ResultDialog({ result, categories, close, saved, refresh, historical }: { result: AnalysisResult; categories: string[]; close: () => void; saved: () => void; refresh: () => void; historical: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [category, setCategory] = useState(result.override_category || result.category);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  useEffect(() => { ref.current?.showModal(); const dialog = ref.current; return () => dialog?.close(); }, []);
  async function save() {
    if (busy || conflict || reason.trim().length < 3 || !category) return;
    setError(""); setConflict(false); setBusy(true);
    try {
      await api(`/appeals/${result.appeal_id}/category`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category, version: result.version, reason: reason.trim() }) });
      saved();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось сохранить категорию"); setConflict(e instanceof ApiError && e.status === 409); }
    finally { setBusy(false); }
  }
  const options = Array.from(new Set([...(categories || []), result.category, result.override_category || ""].filter(Boolean)));
  return <dialog ref={ref} className="appeal-dialog analysis-dialog" aria-labelledby="result-title" onCancel={e => { e.preventDefault(); if (!busy) close(); }} onClick={e => { if (e.target === e.currentTarget && !busy) close(); }}><div className="dialog-content">
    <div className="dialog-heading"><div><p className="eyebrow">ОБОСНОВАНИЕ КЛАССИФИКАЦИИ</p><h2 id="result-title">{result.source_record_id}</h2></div><button className="icon-button" aria-label="Закрыть результат" onClick={close} disabled={busy}><X size={20} /></button></div>
    <div className="dialog-badges"><span className={`badge ${result.status === "analyzed" ? "badge-blue" : "badge-amber"}`}>{resultStatusLabel(result.status)}</span><span className="badge badge-neutral">Входная версия {result.input_version}</span>{historical && <span className="badge badge-amber">Исторический запуск</span>}</div>
    <div className="detail-metadata"><div><span>Категория в запуске</span><strong>{result.category || "Не определена"}</strong></div><div><span>Метод классификации</span><strong>{methodLabel(result.classification_method)}</strong></div><div><span>Оценка метода · не вероятность</span><strong>{scoreLabel(result.score)}</strong></div><div><span>Нормализованная территория</span><strong>{result.territory || "Не определена"}</strong></div></div>
    <div className="detail-body"><h3>Текст, использованный при анализе</h3><p>{result.text}</p></div><div className="detail-address"><MapPin size={16} /><span>{result.address || "Адрес не указан"} · {date(result.date)}</span></div>
    <Notes items={result.explanations} /><Notes items={result.uncertainties} warning />
    {result.duplicate_kind === "republication_candidate" && <div className="analysis-inline-note"><GitBranch size={16} /><p>Вероятная перепубликация. Связанное обращение: <code>{result.duplicate_of || "не указано"}</code>. Совпадение текста не устанавливает личность автора.</p></div>}
    {result.requires_reanalysis && <div className="analysis-inline-note analysis-inline-warning"><RefreshCw size={17} /><p>{result.override_category ? <>Текущая ручная категория: <strong>{result.override_category}</strong>. </> : "Текст или адрес изменился после запуска. "}Категория запуска и группы остаются историческими до повторного анализа.</p></div>}
    {error && <ErrorBox message={error} />}{conflict && <button className="button button-white" onClick={refresh}><RefreshCw size={15} />Обновить результаты</button>}
    {result.status !== "blocked" && !historical ? <div className="category-form"><h3><PencilLine size={15} />Ручная коррекция категории</h3><label className="field"><span>Категория аналитика</span><div className="select-wrap"><select value={category} onChange={e => setCategory(e.target.value)} disabled={busy}>{options.map(value => <option key={value} value={value}>{value}</option>)}</select><ChevronDown size={14} /></div></label><label className="field"><span>Причина изменения *</span><textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} maxLength={500} placeholder="Какой фрагмент обращения подтверждает выбранную категорию?" disabled={busy} /></label><p>Правка сохраняется отдельно. Для обновления групп после неё запустите анализ повторно.</p></div> : <p className="detail-disclaimer">{historical ? "Вы просматриваете историю. Для коррекции выберите последний запуск." : "Перед классификацией необходимо проверить обезличивание обращения."}</p>}
    <div className="dialog-actions"><button className="button button-white" onClick={close} disabled={busy}>Закрыть</button>{result.status === "blocked" ? <Link className="button button-primary" href="/appeals?privacy_status=review_required">Проверить обезличивание <ArrowRight size={15} /></Link> : !historical && <button className="button button-primary" onClick={save} disabled={busy || conflict || reason.trim().length < 3 || !category}>{busy ? <LoaderCircle size={15} className="spin" /> : <CheckCircle2 size={15} />}Сохранить категорию</button>}</div>
  </div></dialog>;
}

function EvidenceItem({ item }: { item: GroupEvidence }) {
  const snapshot = item.analysis;
  const changed = !!snapshot && (item.appeal_version ?? item.version) !== snapshot.input_version;
  return <article className="evidence-item">
    <div className="evidence-item-heading"><strong>{snapshot?.source_record_id || item.source_record_id}</strong><span>{snapshot?.source || item.source} · {date(snapshot?.date || item.date)}</span></div>
    <small className="evidence-snapshot-label">Текст в выбранном запуске{snapshot ? ` · входная версия ${snapshot.input_version}` : ""}</small>
    <p>{snapshot?.text ?? item.text}</p>
    <div className="evidence-item-meta"><span><MapPin size={12} />{snapshot?.address || item.address || "Адрес не указан"}</span><PrivacyBadge status={snapshot?.privacy_status || item.privacy_status} /></div>
    {snapshot && <>
      <div className="evidence-analysis"><span>{snapshot.category}</span><span>{methodLabel(snapshot.classification_method)} · {scoreLabel(snapshot.score)}</span><span>Входная версия {snapshot.input_version}</span>{snapshot.duplicate_kind === "republication_candidate" && <span className="badge badge-amber">Вероятная перепубликация</span>}</div>
      {changed && <><p className="evidence-stale">Обращение изменилось после запуска. Основания группы относятся к показанному выше снимку, а не к текущей версии.</p><details className="evidence-current"><summary>Текущая версия {item.appeal_version ?? item.version}</summary><p>{item.text}</p><div><MapPin size={12} />{item.address || "Адрес не указан"}</div><PrivacyBadge status={item.privacy_status} /></details></>}
      {snapshot.requires_reanalysis && snapshot.override_category && <p className="evidence-stale">Текущая ручная категория: {snapshot.override_category}. Группа ещё не пересчитана.</p>}
      <Notes items={snapshot.explanations} /><Notes items={snapshot.uncertainties} warning />
    </>}
    <small>ID: {item.id}</small>
  </article>;
}

function GroupDialog({ group, close, stale }: { group: AnalysisGroup; close: () => void; stale: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [evidence, setEvidence] = useState<GroupEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { ref.current?.showModal(); const dialog = ref.current; return () => dialog?.close(); }, []);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setEvidence(await api<GroupEvidence[]>(`/groups/${group.id}/appeals`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить доказательства"); }
    finally { setLoading(false); }
  }, [group.id]);
  useEffect(() => { void load(); }, [load]);
  return <dialog ref={ref} className="appeal-dialog analysis-dialog evidence-dialog" aria-labelledby="group-title" onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === e.currentTarget) close(); }}><div className="dialog-content"><div className="dialog-heading"><div><p className="eyebrow">{group.kind === "case" ? "ЛОКАЛЬНЫЙ СЛУЧАЙ" : "ПОВТОРЯЮЩАЯСЯ ПРОБЛЕМА"} · {shortId(group.id)}</p><h2 id="group-title">{group.category}</h2></div><button className="icon-button" aria-label="Закрыть группу" onClick={close}><X size={20} /></button></div><div className="dialog-badges"><span className="badge badge-blue">{groupStatusLabel(group.status)}</span>{stale && <span className="badge badge-amber">Исторический состав</span>}<span className="badge badge-neutral">Версия {group.version}</span></div><div className="detail-address"><MapPin size={17} /><span>{group.territory || "Территория не определена"}</span></div><div className="detail-metadata"><div><span>Период</span><strong>{date(group.start_date)} — {date(group.end_date)}</strong></div><div><span>Минимальное попарное сходство</span><strong>{scoreLabel(group.minimum_similarity)}</strong></div><div><span>Сообщения / источники</span><strong>{number(group.message_count)} / {number(group.source_count)}</strong></div><div><span>Публикации без предполагаемых повторов · оценка</span><strong>{number(group.independent_evidence_count)}</strong></div></div><p className="detail-disclaimer">Публикации объединены в предполагаемые цепочки перепубликаций. Их количество — оценка, которая не устанавливает независимость источников или число уникальных жителей. Оценка сходства не является вероятностью общей аварии.</p><Notes items={group.explanations} /><Notes items={group.uncertainties} warning />{group.kind === "problem" && !!group.case_ids?.length && <div className="analysis-id-list"><strong>Входящие случаи</strong>{group.case_ids.map(id => <code key={id} title={id}>{shortId(id)}</code>)}</div>}
      <div className="evidence-heading"><h3><FileText size={16} />Подтверждающие обращения</h3><span>{number(group.message_count)}</span></div>
      {loading ? <Loading label="Загружаем доказательства…" /> : error ? <ErrorBox message={error} retry={load} /> : !evidence.length ? <Empty title="Нет доступных обращений" description="Обновите запуск, чтобы проверить состав группы." /> : <div className="evidence-list">{evidence.map(item => <EvidenceItem key={item.id} item={item} />)}</div>}
      <div className="dialog-actions"><button className="button button-white" onClick={close}>Закрыть карточку</button><Link className="button button-primary" href={`/problems/${group.id}`}>Решение аналитика <ArrowRight size={15} /></Link></div>
    </div></dialog>;
}

function GroupCard({ group, open }: { group: AnalysisGroup; open: () => void }) {
  return <article className="analysis-group-card"><div className="group-card-top"><span className={`group-icon ${group.kind === "problem" ? "group-icon-violet" : ""}`}>{group.kind === "problem" ? <GitBranch size={21} /> : <Layers3 size={21} />}</span><span className="badge badge-neutral">{groupStatusLabel(group.status)}</span><span className="group-short-id">#{shortId(group.id)}</span></div><h3>{group.category}</h3><div className="group-location"><MapPin size={14} />{group.territory || "Территория не определена"}</div><div className="group-period"><CalendarDays size={13} />{date(group.start_date)} — {date(group.end_date)}</div><div className="group-counts"><div><strong>{number(group.message_count)}</strong><span>сообщений</span></div><div><strong>{number(group.source_count)}</strong><span>источников</span></div><div><strong>{number(group.independent_evidence_count)}</strong><span>публикаций*</span></div></div><p className="group-explanation">{group.explanations[0] || "Основания доступны в карточке группы."}</p>{group.uncertainties.length > 0 && <div className="group-warning"><AlertTriangle size={13} />{group.uncertainties.length} замечаний к объединению</div>}<button className="group-open" onClick={open}>Проверить доказательства <ArrowRight size={15} /></button></article>;
}

export default function AnalysisPage() {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [runId, setRunId] = useState("");
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [cases, setCases] = useState<AnalysisGroup[]>([]);
  const [problems, setProblems] = useState<AnalysisGroup[]>([]);
  const [issues, setIssues] = useState<AnalysisIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dataError, setDataError] = useState("");
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [tab, setTab] = useState<Tab>("cases");
  const [query, setQuery] = useState("");
  const [onlyUncertain, setOnlyUncertain] = useState(false);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [selectedResult, setSelectedResult] = useState<AnalysisResult | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<AnalysisGroup | null>(null);
  const loadStatus = useCallback(async (chooseLatest = false) => {
    setError("");
    try {
      const [state, history] = await Promise.all([api<AnalysisStatus>("/analysis/status"), api<AnalysisRun[]>("/analysis/runs")]);
      setStatus(state);
      setRuns(state.latest_run && !history.some(item => item.id === state.latest_run?.id) ? [state.latest_run, ...history] : history);
      setRunId(current => chooseLatest || !current ? state.latest_run?.id || "" : current);
      return state;
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка загрузки анализа"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void loadStatus(); }, [loadStatus]);
  useEffect(() => {
    if (!runId) { setResults([]); setCases([]); setProblems([]); setIssues([]); return; }
    let live = true; setDataLoading(true); setDataError("");
    const suffix = `run_id=${encodeURIComponent(runId)}`;
    Promise.all([api<AnalysisResult[]>(`/analysis/results?${suffix}`), api<AnalysisGroup[]>(`/groups?${suffix}&kind=case`), api<AnalysisGroup[]>(`/groups?${suffix}&kind=problem`), api<AnalysisIssue[]>(`/analysis/issues?${suffix}`)]).then(([items, localCases, recurring, attention]) => { if (live) { setResults(items); setCases(localCases); setProblems(recurring); setIssues(attention); } }).catch(e => { if (live) setDataError(e instanceof Error ? e.message : "Ошибка результатов"); }).finally(() => { if (live) setDataLoading(false); });
    return () => { live = false; };
  }, [runId, reload]);
  useEffect(() => {
    if (status?.latest_run?.status !== "running") return;
    const timer = setInterval(async () => { const fresh = await loadStatus(); if (fresh?.latest_run?.status !== "running") setReload(v => v + 1); }, 3000);
    return () => clearInterval(timer);
  }, [status?.latest_run?.status, loadStatus]);
  useEffect(() => { setPage(1); }, [query, onlyUncertain, runId, tab]);
  const run = runs.find(item => item.id === runId) || (status?.latest_run?.id === runId ? status.latest_run : null);
  const historical = !!run && run.id !== status?.latest_run?.id;
  const running = busy || status?.latest_run?.status === "running";
  async function analyze(retry = false) {
    if (running) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const endpoint = retry && run ? `/analysis/runs/${run.id}/retry` : "/analysis/run";
      const value = await api<AnalysisRun>(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      await loadStatus(true); setRunId(value.id); setReload(v => v + 1);
      if (value.status === "failed") setError("Запуск завершился с ошибкой. Подробности сохранены ниже.");
      else setNotice("Результаты запуска сохранены. Проверьте предложенные категории и группы.");
    } catch (e) { await loadStatus(); setError(e instanceof Error ? e.message : "Не удалось выполнить анализ"); }
    finally { setBusy(false); }
  }
  const filteredResults = results.filter(item => {
    const matches = `${item.source_record_id} ${item.text} ${item.category} ${item.override_category || ""} ${item.territory || ""}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru"));
    return matches && (!onlyUncertain || item.uncertainties.length > 0 || item.status !== "analyzed" || item.requires_reanalysis);
  });
  const groups = tab === "cases" ? cases : problems;
  const filteredGroups = groups.filter(item => `${item.category} ${item.territory || ""} ${item.id}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")) && (!onlyUncertain || item.uncertainties.length > 0));
  const count = tab === "results" ? filteredResults.length : filteredGroups.length;
  useEffect(() => { setPage(current => Math.min(current, Math.max(1, Math.ceil(count / 20)))); }, [count]);
  const stale = !!run?.stale || results.some(item => item.requires_reanalysis);
  return <>
    <PageTitle eyebrow="КЛАССИФИКАЦИЯ И СВЯЗАННЫЕ ОБРАЩЕНИЯ" title="AI-анализ" description="Категории, локальные случаи и повторяющиеся проблемы с проверяемыми основаниями."><button className="button button-white button-icon" aria-label="Обновить анализ" disabled={running} onClick={() => { void loadStatus(); setReload(v => v + 1); }}><RefreshCw size={16} /></button><Link href="/problems" className="button button-white">Все группы <ArrowRight size={15} /></Link></PageTitle>
    {error && <ErrorBox message={error} retry={() => void loadStatus()} />}
    {notice && <div className="success-notice" role="status"><CheckCircle2 size={17} />{notice}<button className="icon-button" aria-label="Скрыть уведомление" onClick={() => setNotice("")}><X size={15} /></button></div>}
    <section className="analysis-launch panel"><div className="analysis-launch-copy"><div className="analysis-method-icon"><Sparkles size={24} /></div><div><p className="eyebrow">МЕТОД ДЛЯ НОВОГО ЗАПУСКА</p><h2>{status ? availableAlgorithmLabel(status.algorithm) : "Проверяем доступность метода…"}</h2><p>{status?.algorithm.semantic && status.algorithm.model_load_verified !== true ? "Локальные файлы модели обнаружены. Загрузка будет проверена при запуске; при сбое используется TF-IDF. Фактический метод будет указан в результате." : status?.algorithm.semantic ? "Мультиязычное смысловое сходство с учётом территории и времени." : "Лексическое сходство и словарные правила. Перефразировки между языками могут остаться несвязанными."}</p>{status?.algorithm.fallback_reason && <p className="fallback-reason">{status.algorithm.fallback_reason}</p>}{status?.algorithm.model_id && status.algorithm.semantic && <code className="model-id">{status.algorithm.model_id}</code>}</div></div><div className="analysis-launch-controls"><label className="field"><span>Режим нового запуска</span><div className="select-wrap"><select value={mode} disabled={running} onChange={e => setMode(e.target.value as Mode)}><option value="auto">Автоматически: E5 или резервный метод</option><option value="tfidf">TF-IDF · только текстовый метод</option></select><ChevronDown size={14} /></div></label><button className="button button-primary" disabled={running || !status || status.total_appeals === 0} onClick={() => analyze()}>{running ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}{running ? "Анализ выполняется…" : status?.latest_run ? "Запустить новый анализ" : "Запустить анализ"}</button><small>{status ? `${number(status.total_appeals)} обращений в реестре · ${number(status.pending_appeals)} ожидают анализа` : "Подключение к локальному серверу"}</small></div></section>
    {running && <div className="analysis-inline-note" role="status"><LoaderCircle size={18} className="spin" /><p>Обрабатываем локальные данные. Загрузка модели и расчёт сходства могут занять время. Процент готовности сервер не сообщает.</p></div>}
    {loading || (running && !status?.latest_run) ? <Loading label={running ? "Вычисляем категории и связи…" : "Загружаем состояние анализа…"} /> : !status ? null : !status.latest_run ? <section className="panel"><Empty title="Готово к первому анализу" description={status?.total_appeals ? "Запустите обработку. Записи с непроверенными личными сведениями будут исключены из анализа." : "Сначала импортируйте обращения, затем запустите анализ этого реестра."} action={!status?.total_appeals ? <ImportLink /> : <Link className="text-button" href="/appeals?privacy_status=review_required">Проверить обезличивание <ArrowRight size={15} /></Link>} /></section> : <>
      <div className="analysis-runbar"><div className="run-select"><History size={17} /><label htmlFor="analysis-run">Запуск</label><select id="analysis-run" value={runId} onChange={e => setRunId(e.target.value)} disabled={running}>{runs.map(item => <option key={item.id} value={item.id}>{date(item.created_at)} · {shortId(item.id)} · {runStatusLabel(item.status)}</option>)}</select><ChevronDown size={14} /></div>{run && <span className={`badge ${run.status === "failed" ? "badge-amber" : "badge-green"}`}>{runStatusLabel(run.status)}</span>}{historical && <span className="badge badge-neutral">История</span>}</div>
      {run && <><div className="analysis-run-method"><span>Метод выбранного запуска</span><strong>{algorithmLabel(run.algorithm)}</strong><small>{run.finished_at ? `Завершён ${date(run.finished_at)}` : "Время завершения не указано"}</small></div><section className="analysis-metrics" aria-label="Результаты выбранного запуска"><div><FileText size={17} /><strong>{number(run.analyzed)}</strong><span>обработано из {number(run.total)}</span></div><div><Layers3 size={17} /><strong>{number(run.case_count)}</strong><span>локальных случаев</span></div><div><GitBranch size={17} /><strong>{number(run.problem_count)}</strong><span>повторяющихся проблем</span></div><div><ShieldCheck size={17} /><strong>{number(run.blocked)}</strong><span>не допущено к анализу</span></div><div className={run.uncertainties_count || run.error_count ? "metric-attention" : ""}><CircleHelp size={17} /><strong>{number(run.uncertainties_count)}</strong><span>с неопределённостями · ошибок {number(run.error_count)}</span></div></section></>}
      {(stale || historical) && <div className="analysis-inline-note analysis-inline-warning"><AlertTriangle size={18} /><div><strong>{historical ? "Вы просматриваете предыдущий запуск" : "Данные или решения изменились после анализа"}</strong><p>Категории и состав групп относятся к сохранённому запуску. Повторный анализ создаст новый результат и сохранит историю.</p></div><button className="button button-white" disabled={running} onClick={() => analyze(true)}><RefreshCw size={14} />Пересчитать</button></div>}
      {!!run?.errors?.length && <div className="analysis-errors"><strong><AlertTriangle size={15} />Ошибки выбранного запуска</strong><ul>{run.errors.map((item, i) => <li key={i}>{typeof item === "string" ? item : item.message || item.error || "Ошибка обработки обращения"}{typeof item !== "string" && item.appeal_id ? ` · ${shortId(item.appeal_id)}` : ""}</li>)}</ul><button className="text-button" disabled={running} onClick={() => analyze(true)}>Повторить запуск <RefreshCw size={13} /></button></div>}
      {!dataLoading && issues.length > 0 && <details className="analysis-issues"><summary><AlertTriangle size={15} /><span>Что требует внимания</span><strong>{number(issues.length)}</strong><ChevronDown size={15} /></summary><div className="analysis-issues-list">{issues.map((issue, index) => <div key={index}><span className="badge badge-amber">{issueLabel(issue.kind)}</span><p>{issue.message}</p>{issue.appeal_id && <button className="text-button" onClick={() => { const result = results.find(item => item.appeal_id === issue.appeal_id); if (result) setSelectedResult(result); }} disabled={!results.some(item => item.appeal_id === issue.appeal_id)}>Обращение {results.find(item => item.appeal_id === issue.appeal_id)?.source_record_id || shortId(issue.appeal_id)} <ChevronRight size={12} /></button>}</div>)}</div></details>}
      <section className="panel analysis-results"><div className="analysis-tabs" role="tablist" aria-label="Виды результатов"><button role="tab" aria-selected={tab === "cases"} onClick={() => setTab("cases")} className={tab === "cases" ? "active" : ""}><Layers3 size={16} />Локальные случаи <span>{cases.length}</span></button><button role="tab" aria-selected={tab === "problems"} onClick={() => setTab("problems")} className={tab === "problems" ? "active" : ""}><GitBranch size={16} />Повторяющиеся проблемы <span>{problems.length}</span></button><button role="tab" aria-selected={tab === "results"} onClick={() => setTab("results")} className={tab === "results" ? "active" : ""}><ListFilter size={16} />Обращения <span>{results.length}</span></button></div><div className="analysis-tab-description">{tab === "cases" ? "Предположительно один случай в близком месте и времени. Одинаковая тема сама по себе не является основанием для объединения." : tab === "problems" ? "Связанные локальные случаи, повторяющиеся во времени. Общая категория не означает одну аварию." : "Категория, использованный метод, версия входных данных и объяснение для каждого обращения."}</div><div className="analysis-results-toolbar"><label className="search-field"><Search size={17} /><input value={query} onChange={e => setQuery(e.target.value)} aria-label="Поиск в результатах анализа" placeholder={tab === "results" ? "Текст, ID, категория или территория…" : "Категория или территория…"} maxLength={200} />{query && <button className="icon-button" aria-label="Сбросить поиск анализа" onClick={() => setQuery("")}><X size={14} /></button>}</label><label className="checkbox-label"><input type="checkbox" checked={onlyUncertain} onChange={e => setOnlyUncertain(e.target.checked)} />Только с замечаниями</label></div>
      {dataLoading || run?.status === "running" ? <Loading label={run?.status === "running" ? "Ждём завершения выбранного запуска…" : "Загружаем результаты запуска…"} /> : dataError ? <ErrorBox message={dataError} retry={() => setReload(v => v + 1)} /> : run?.status === "failed" ? <Empty title="Результаты запуска не сохранены" description="Проверьте ошибку выше. Можно повторить обработку текущих данных или выбрать завершённый запуск из истории." /> : !count ? <Empty title={query || onlyUncertain ? "Нет результатов по выбранным условиям" : tab === "cases" ? "Локальные случаи не выделены" : tab === "problems" ? "Повторяющиеся проблемы не выделены" : "Нет результатов классификации"} description={query || onlyUncertain ? "Измените запрос или отключите фильтр замечаний." : "Алгоритм оставляет обращения раздельными, если данных или сходства недостаточно. Проверьте вкладку обращений и неопределённости."} /> : tab === "results" ? <div className="table-scroll"><table className="data-table analysis-table"><thead><tr><th>Обращение</th><th>Категория / метод</th><th>Оценка метода</th><th>Результат</th><th><span className="sr-only">Просмотр</span></th></tr></thead><tbody>{filteredResults.slice((page - 1) * 20, page * 20).map(item => <tr key={item.id}><td className="analysis-result-text"><strong>{item.source_record_id}</strong><button className="appeal-link" onClick={() => setSelectedResult(item)}>{item.text}</button><small>{date(item.date)} · {item.territory || "Территория неизвестна"} · вход v{item.input_version}</small></td><td><strong>{item.category || "Не определена"}</strong><small>{methodLabel(item.classification_method)}</small>{item.override_category && <span className="manual-category"><PencilLine size={11} />Правка: {item.override_category}</span>}</td><td><strong>{scoreLabel(item.score)}</strong><small>Не вероятность</small></td><td><span className={`badge ${item.status === "analyzed" ? "badge-blue" : "badge-amber"}`}>{resultStatusLabel(item.status)}</span>{item.duplicate_kind === "republication_candidate" && <small>Вероятная перепубликация</small>}{item.uncertainties.length > 0 && <small>{item.uncertainties.length} неопределённостей</small>}{item.requires_reanalysis && <small className="analysis-stale-label">Нужен пересчёт</small>}</td><td><button className="icon-button" aria-label={`Результат ${item.source_record_id}`} onClick={() => setSelectedResult(item)}><ChevronRight size={17} /></button></td></tr>)}</tbody></table></div> : <div className="analysis-group-grid">{filteredGroups.slice((page - 1) * 20, page * 20).map(group => <GroupCard key={group.id} group={group} open={() => setSelectedGroup(group)} />)}</div>}
      {!dataLoading && !dataError && count > 0 && <div className="table-footer"><span>{(page - 1) * 20 + 1}–{Math.min(page * 20, count)} из {number(count)}</span><div className="pagination"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={14} />Назад</button><span>Страница {page}</span><button disabled={page * 20 >= count} onClick={() => setPage(value => value + 1)}>Вперёд<ChevronRight size={14} /></button></div></div>}
      </section><div className="analysis-footnote"><CircleHelp size={16} /><p>* Публикации без предполагаемых повторов — оценка после обнаружения перепубликаций. Она не устанавливает независимость источников или число уникальных жителей. Категории и группы являются предложениями для проверки аналитиком. Оценки разных методов не следует сравнивать как вероятности.</p></div>
    </>}
    {selectedResult && <ResultDialog result={selectedResult} categories={status?.categories || []} historical={historical} close={() => setSelectedResult(null)} refresh={() => { setSelectedResult(null); void loadStatus(); setReload(v => v + 1); }} saved={() => { setSelectedResult(null); setNotice("Категория сохранена. Пересчитайте анализ, чтобы обновить группы."); void loadStatus(); setReload(v => v + 1); }} />}
    {selectedGroup && <GroupDialog group={selectedGroup} close={() => setSelectedGroup(null)} stale={stale || historical} />}
  </>;
}
