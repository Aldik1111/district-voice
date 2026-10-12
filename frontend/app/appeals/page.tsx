"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, FileText, LoaderCircle, MapPin, Search, ShieldCheck, X } from "lucide-react";
import { api, Appeal, date, number } from "@/lib/api";
import { Empty, ErrorBox, ImportLink, Loading, PageTitle, PrivacyBadge } from "@/components/ui";

import { RegistryAppeal, RegistryPage, analysisStateLabel, useResource } from "@/lib/workspace";
import { CategoryBadge, RunScope } from "@/components/workspace-ui";

function AppealDetails({ appeal, close, saved }: { appeal: RegistryAppeal; close: () => void; saved: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(appeal.text);
  const [address, setAddress] = useState(appeal.address || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  async function save() {
    if (!confirmed || !text.trim()) return;
    setBusy(true); setError("");
    try {
      await api<Appeal>(`/appeals/${appeal.id}/privacy`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text.trim(), address: address.trim(), version: appeal.version }) });
      saved();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось сохранить изменения"); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialogRef} className="appeal-dialog" onCancel={e => { e.preventDefault(); if (!busy) close(); }} onClick={e => { if (e.target === e.currentTarget && !busy) close(); }} aria-labelledby="appeal-dialog-title"><div className="dialog-content"><div className="dialog-heading"><div><p className="eyebrow">ОБРАЩЕНИЕ #{appeal.id}</p><h2 id="appeal-dialog-title">{appeal.source_record_id}</h2></div><button className="icon-button" aria-label="Закрыть карточку" onClick={close} disabled={busy}><X size={20} /></button></div><div className="dialog-badges"><CategoryBadge category={appeal.category} /><PrivacyBadge status={appeal.privacy_status} /><span className="badge badge-neutral">{appeal.language === "kk" ? "Қазақша" : appeal.language === "ru" ? "Русский" : appeal.language || "Язык не определён"}</span></div><div className="detail-metadata"><div><span>Источник</span><strong>{appeal.source}</strong></div><div><span><CalendarDays size={13} /> Дата обращения</span><strong>{date(appeal.date)}</strong></div><div><span>Официальный статус</span><strong>{appeal.official_status || "Не указан"}</strong></div><div><span>AI-анализ</span><strong>{appeal.analysis_status === "running" ? "Выполняется" : appeal.analysis_status === "failed" ? "Ошибка анализа" : appeal.analysis_status === "analyzed" ? "Обработано" : appeal.analysis_status === "blocked" ? "Нужна проверка обезличивания" : appeal.analysis_status === "review_required" ? "Нужна оценка аналитика" : "Ожидает анализа"} · <Link className="text-button" href="/analysis">Результаты</Link></strong></div></div>
    {error && <ErrorBox message={error} />}
    {editing ? <div className="review-form"><div className="inline-notice"><ShieldCheck size={18} /><p>Уберите личные сведения из текста и адреса. Сохраняйте описание проблемы и общественно значимое местоположение.</p></div><label className="field"><span>Обезличенный текст *</span><textarea rows={7} maxLength={20000} value={text} disabled={busy} onChange={e => setText(e.target.value)} /></label><label className="field"><span>Обезличенный адрес</span><input value={address} maxLength={500} disabled={busy} onChange={e => setAddress(e.target.value)} /></label><label className="checkbox-label review-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />Я проверил(а) текст и адрес на персональные сведения</label></div> : <><div className="detail-body"><h3>Текст обращения</h3><p>{appeal.text}</p></div><div className="detail-address"><MapPin size={17} /><span>{appeal.address || "Адрес не указан"}</span></div>{appeal.warnings.length > 0 && <div className="review-warnings"><strong>Замечания автоматической проверки</strong>{appeal.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</div>}<p className="detail-disclaimer">Представлено после автоматического маскирования. Это не гарантирует отсутствия персональных сведений.</p></>}
    {!!appeal.groups.length && <div className="record-groups"><strong>Связанные группы</strong>{appeal.groups.map(group => <Link className="text-button" href={`/problems/${group.id}`} key={group.id}>{group.kind === "problem" ? "Повторяющаяся проблема" : "Локальный случай"}: {group.category}<ArrowRight size={14} /></Link>)}{appeal.requires_reanalysis && <small>Связи относятся к прежней версии данных. Требуется повторный анализ.</small>}</div>}
    <div className="dialog-actions">{editing ? <><button className="button button-white" onClick={() => setEditing(false)} disabled={busy}>Отмена</button><button className="button button-primary" onClick={save} disabled={busy || !confirmed || !text.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <CheckCircle2 size={16} />}Сохранить проверку</button></> : <><button className="button button-white" onClick={close}>Закрыть</button><button className="button button-primary" onClick={() => setEditing(true)}><ShieldCheck size={16} />Проверить личные сведения</button></>}</div></div></dialog>;
}

function Appeals() {
  const searchParams = useSearchParams();
  return <AppealRegistry key={searchParams.toString()} initialQuery={searchParams.get("q") || ""} initialPrivacy={searchParams.get("privacy_status") || ""} />;
}

function AppealRegistry({ initialQuery, initialPrivacy }: { initialQuery: string; initialPrivacy: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [privacy, setPrivacy] = useState(initialPrivacy);
  const [category, setCategory] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<RegistryAppeal | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedQuery(query); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [query]);
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (debouncedQuery.trim()) params.set("q", debouncedQuery.trim());
  if (privacy) params.set("privacy_status", privacy);
  if (category) params.set("category", category);
  if (source) params.set("source", source);
  if (status) params.set("analysis_status", status);
  const { data, loading, error, reload } = useResource<RegistryPage>(`/registry?${params}`);
  // Keep available filter options visible while a new query is in flight.
  const [options, setOptions] = useState<{ categories: string[]; sources: string[] }>({ categories: [], sources: [] });
  useEffect(() => { if (data) setOptions({ categories: data.categories, sources: data.sources }); }, [data]);
  const close = useCallback(() => setSelected(null), []);
  const filtered = !!(privacy || debouncedQuery || category || source || status);
  const reset = () => { setQuery(""); setPrivacy(""); setCategory(""); setSource(""); setStatus(""); setPage(1); };
  return <>
    <PageTitle eyebrow="ЕДИНЫЙ РЕЕСТР" title="Все обращения" description="От сообщения к результату: обезличенные тексты, категории и найденные связи."><ImportLink>Добавить обращения</ImportLink></PageTitle>
    {notice && <div className="success-notice" role="status"><CheckCircle2 size={18} />{notice}<button className="icon-button" aria-label="Скрыть уведомление" onClick={() => setNotice("")}><X size={16} /></button></div>}
    <div className="registry-notice"><span className="note-icon"><ShieldCheck size={19} /></span><div><strong>Обезличивание с ручной проверкой</strong><p>Показан текст после маскирования. Проверьте записи с отметкой «Нужна проверка».</p></div><button className="text-button" onClick={() => { setPrivacy("review_required"); setPage(1); }}>К проверке <ArrowRight size={16} /></button></div>
    {data?.run?.stale && <RunScope run={data.run} />}
    <section className="panel registry-panel"><div className="registry-toolbar"><label className="search-field"><Search size={18} /><input placeholder="Поиск по тексту, адресу или ID…" aria-label="Поиск обращений" maxLength={200} value={query} onChange={e => setQuery(e.target.value)} />{query && <button className="icon-button" aria-label="Очистить поиск" onClick={() => setQuery("")}><X size={15} /></button>}</label>{filtered && <button className="text-button" onClick={reset}>Сбросить фильтры</button>}</div>
      <div className="registry-filters">
        <label className="field"><span>Категория</span><select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}><option value="">Все категории</option>{options.categories.map(item => <option key={item}>{item}</option>)}</select></label>
        <label className="field"><span>Источник</span><select value={source} onChange={e => { setSource(e.target.value); setPage(1); }}><option value="">Все источники</option>{options.sources.map(item => <option key={item}>{item}</option>)}</select></label>
        <label className="field"><span>Статус анализа</span><select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">Любой статус</option>{["pending", "analyzed", "review_required", "blocked", "failed"].map(item => <option key={item} value={item}>{analysisStateLabel(item)}</option>)}</select></label>
        <label className="field"><span>Проверка данных</span><select value={privacy} onChange={e => { setPrivacy(e.target.value); setPage(1); }}><option value="">Все записи</option><option value="review_required">Нужна проверка</option><option value="masked">Данные скрыты</option><option value="clear">Признаков не найдено</option></select></label>
      </div><div className="registry-meta"><span><strong>{data ? number(data.total) : "—"}</strong> обращений{filtered ? " по выбранным условиям" : " в реестре"}</span><span>По дате обращения · сначала новые</span></div>
    {error ? <ErrorBox message={error} retry={reload} /> : loading ? <Loading label="Загружаем обращения…" /> : data?.items.length ? <><div className="table-scroll"><table className="data-table appeals-table"><thead><tr><th>ID / дата</th><th>Текст обращения</th><th>Категория</th><th>Район / адрес</th><th>Источник</th><th>Статус анализа</th><th><span className="sr-only">Действие</span></th></tr></thead><tbody>{data.items.map(appeal => <tr key={appeal.id}>
      <td className="appeal-id"><strong>{appeal.source_record_id}</strong><small>{date(appeal.date)}</small><small className="technical-id" title={appeal.id}>#{appeal.id.slice(0, 8)}</small></td>
      <td className="appeal-text"><button className="appeal-link" onClick={() => setSelected(appeal)}>{appeal.text}</button><PrivacyBadge status={appeal.privacy_status} /></td>
      <td><CategoryBadge category={appeal.category} />{appeal.classification_method === "manual_override" && <small>Уточнено вручную</small>}</td>
      <td className="registry-address">{appeal.address || "Адрес не указан"}</td><td><span className="source-chip">{appeal.source}</span><small>{appeal.language === "kk" ? "Қазақша" : appeal.language === "ru" ? "Русский" : appeal.language}</small></td>
      <td><span className={`analysis-status ${appeal.analysis_status === "analyzed" ? "status-complete" : ""}`}>{analysisStateLabel(appeal.analysis_status)}</span>{appeal.requires_reanalysis && <small className="stale-text">Нужен пересчёт</small>}{appeal.groups.map(group => <Link className="record-group-link" key={group.id} href={`/problems/${group.id}`}>{group.kind === "problem" ? "Системная проблема" : "Локальный случай"}<ArrowRight size={12} /></Link>)}</td>
      <td><button className="icon-button" aria-label={`Открыть обращение ${appeal.source_record_id}`} onClick={() => setSelected(appeal)}><ChevronRight size={18} /></button></td></tr>)}</tbody></table></div><div className="table-footer"><span>{(page - 1) * data.page_size + 1}–{Math.min(page * data.page_size, data.total)} из {number(data.total)}</span><div className="pagination"><button disabled={page === 1} aria-label="Предыдущая страница" onClick={() => setPage(p => p - 1)}><ChevronLeft size={15} />Назад</button><span>Страница {page}</span><button disabled={page * data.page_size >= data.total} aria-label="Следующая страница" onClick={() => setPage(p => p + 1)}>Вперёд<ChevronRight size={15} /></button></div></div></> : <Empty title={filtered ? "Обращения не найдены" : "Реестр готов к работе"} description={filtered ? "Измените поисковый запрос или условия фильтрации." : "Загрузите первую партию CSV или Excel. Сохранённые обращения появятся здесь."} action={filtered ? <button className="button button-white" onClick={reset}>Сбросить фильтры</button> : <ImportLink />} />}</section>
    <div className="registry-footnote"><FileText size={15} /><p>Категории и группы относятся к последнему успешному анализу. После изменения данных выполните <Link className="text-button" href="/analysis">повторный анализ</Link>.</p></div>
    {selected && <AppealDetails key={selected.id} appeal={selected} close={close} saved={() => { setSelected(null); setNotice("Проверка сохранена. Данные обращения обновлены."); reload(); }} />}
  </>;
}

export default function AppealsPage() { return <Suspense fallback={<Loading />}><Appeals /></Suspense>; }
