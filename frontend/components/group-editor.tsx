"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, LoaderCircle, X } from "lucide-react";
import { api, date, shortId } from "@/lib/api";
import { AnalysisGroup, AnalysisStatus, GroupEvidence } from "@/lib/analysis";
import { RegistryPage, ReviewedGroup, useResource } from "@/lib/workspace";
import { ErrorBox, Loading } from "./ui";

type Action = "edit" | "add" | "remove" | "split" | "merge";
const labels: Record<Action, string> = { edit: "Название и категория", add: "Добавить обращение", remove: "Исключить обращение", split: "Разделить группу", merge: "Объединить группы" };

function Picker({ action, group, checked, setChecked, target, setTarget }: { action: Action; group: ReviewedGroup; checked: string[]; setChecked: (ids: string[]) => void; target: AnalysisGroup | null; setTarget: (group: AnalysisGroup) => void }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const splitCases = action === "split" && group.kind === "problem";
  const path = action === "add" ? `/registry?q=${encodeURIComponent(query)}&page=${page}&page_size=20` : action === "merge" || splitCases ? `/groups?run_id=${group.run_id}` : `/groups/${group.id}/appeals`;
  const { data, loading, error, reload } = useResource<RegistryPage | AnalysisGroup[] | GroupEvidence[]>(path);
  const toggle = (id: string) => setChecked(checked.includes(id) ? checked.filter(value => value !== id) : [...checked, id]);
  return <>
    {action === "add" && <label className="field"><span>Поиск по ID или тексту</span><input value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} placeholder="Найдите обращение в реестре" /></label>}
    {loading ? <Loading /> : error ? <ErrorBox message={error} retry={reload} /> : data && <div className="curation-picker">
      {action === "merge" || splitCases ? (data as AnalysisGroup[]).filter(item => item.id !== group.id && item.kind === (splitCases ? "case" : group.kind) && (!splitCases || group.case_ids?.includes(item.id))).map(item => <label className="curation-option" key={item.id}><input type={splitCases ? "checkbox" : "radio"} name="merge-target" checked={splitCases ? checked.includes(item.id) : target?.id === item.id} onChange={() => splitCases ? toggle(item.id) : setTarget(item)} /><span><strong>{item.title || item.category} · {shortId(item.id)}</strong><small>{item.territory || "Территория неизвестна"} · {date(item.start_date)} · {item.message_count} сообщений</small></span></label>)
        : (action === "add" ? (data as RegistryPage).items : data as GroupEvidence[]).map(item => {
          const occupied = "groups" in item && item.groups.some(value => value.kind === "case");
          return <label className={`curation-option ${occupied ? "unavailable" : ""}`} key={item.id}><input type="checkbox" disabled={occupied || item.privacy_status === "review_required"} checked={checked.includes(item.id)} onChange={() => toggle(item.id)} /><span><strong>{item.source_record_id} · {date(item.date)}</strong><span>{item.text}</span><small>{item.address || "Адрес неизвестен"} · {item.source}</small><code>{item.id}</code>{occupied && <small>Уже в случае: сначала исключите его из прежней группы.</small>}</span></label>;
        })}
      {action === "add" && <div className="pagination"><button type="button" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Назад</button><span>Страница {page}</span><button type="button" disabled={page * 20 >= (data as RegistryPage).total} onClick={() => setPage(value => value + 1)}>Вперёд</button></div>}
    </div>}
  </>;
}

function EditorDialog({ group, action, close, saved }: { group: ReviewedGroup; action: Action; close: () => void; saved: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState(group.title || group.category);
  const [category, setCategory] = useState(group.category);
  const [reason, setReason] = useState("");
  const [checked, setChecked] = useState<string[]>([]);
  const [target, setTarget] = useState<AnalysisGroup | null>(null);
  const [caseId, setCaseId] = useState(group.case_ids?.[0] || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<AnalysisGroup | null>(null);
  const { data: status } = useResource<AnalysisStatus>("/analysis/status");
  useEffect(() => { dialog.current?.showModal(); }, []);
  async function submit() {
    setBusy(true); setError("");
    try {
      const result = await api<{ group: AnalysisGroup; created_group: AnalysisGroup | null }>(`/groups/${group.id}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, version: group.version, reason,
        ...(action === "edit" ? { title, category } : action === "merge" ? { target_id: target?.id, target_version: target?.version } : action === "split" && group.kind === "problem" ? { case_ids: checked } : { appeal_ids: checked, ...(action === "add" && group.kind === "problem" ? { case_id: caseId } : {}) }) }) });
      if (result.created_group) setCreated(result.created_group); else saved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить изменения."); }
    finally { setBusy(false); }
  }
  return <dialog className="appeal-dialog curation-dialog" ref={dialog} onCancel={event => { event.preventDefault(); if (!busy) { if (created) saved(); else close(); } }}><div className="dialog-content"><div className="dialog-heading"><div><p className="section-kicker">ДЕМО-ОПЕРАТОР · ВЕРСИЯ {group.version}</p><h2>{labels[action]}</h2></div><button className="icon-button" aria-label="Закрыть редактирование группы" disabled={busy} onClick={created ? saved : close}><X size={19} /></button></div>
    {created ? <div className="success-notice"><p>Группа разделена. Связи и показатели сохранены.</p><Link className="button button-white" href={`/problems/${created.id}`}>Открыть новую группу <ArrowRight size={16} /></Link><button className="button button-primary" onClick={saved}>Готово</button></div> : <>
      <p className="panel-help">Изменения сохранятся в SQLite. Исходные обращения сохраняются. Решение о группе и связанных проблемах вернётся на проверку, прежнее объяснение AI будет помечено устаревшим.</p>
      {action === "split" && <p className="inline-notice">Выберите {group.kind === "case" ? "обращения" : "связанные случаи"} для новой группы. Остальные останутся в текущей.</p>}
      {action === "merge" && <p className="inline-notice">Выбранная группа перейдёт в архив со ссылкой на текущую. Её обращения и связи будут перенесены в текущую группу.</p>}
      {action === "edit" ? <><label className="field"><span>Название проблемы</span><input maxLength={160} value={title} onChange={event => setTitle(event.target.value)} /></label><label className="field"><span>Категория группы</span><select value={category} onChange={event => setCategory(event.target.value)}>{(status?.categories || [group.category]).map(item => <option key={item}>{item}</option>)}</select></label><p className="small-print">Меняется категория группы. Исходная классификация каждого обращения остаётся в истории анализа.</p></> : <Picker action={action} group={group} checked={checked} setChecked={setChecked} target={target} setTarget={setTarget} />}
      {action === "add" && group.kind === "problem" && <label className="field"><span>В какой связанный случай добавить</span><select value={caseId} onChange={event => setCaseId(event.target.value)}>{group.case_ids?.map(id => <option key={id} value={id}>Случай #{shortId(id)}</option>)}</select></label>}
      <label className="field"><span>Основание изменения</span><textarea rows={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} placeholder="Объясните решение без персональных данных" /></label>
      {error && <ErrorBox message={error} />}
      <div className="dialog-actions"><button className="button button-white" disabled={busy} onClick={close}>Отмена</button><button className="button button-primary" disabled={busy || reason.trim().length < 3 || (action === "edit" ? title.trim().length < 3 : action === "merge" ? !target : !checked.length)} onClick={submit}>{busy && <LoaderCircle size={16} className="spin" />}Сохранить изменения{checked.length > 0 ? ` (${checked.length})` : ""}</button></div>
    </>}
  </div></dialog>;
}

export function GroupEditor({ group, disabled, saved }: { group: ReviewedGroup; disabled: boolean; saved: () => void }) {
  const [action, setAction] = useState<Action | null>(null);
  return <><div className="analyst-actions curation-actions">{(Object.keys(labels) as Action[]).map(item => <button className="button button-white" key={item} disabled={disabled} onClick={() => setAction(item)}>{labels[item]}</button>)}</div><p className="small-print">Без авторизации: все решения подписаны «Демо-оператор».</p>{action && <EditorDialog group={group} action={action} close={() => setAction(null)} saved={() => { setAction(null); saved(); }} />}</>;
}
