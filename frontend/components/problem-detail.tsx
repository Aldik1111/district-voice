"use client";

import { GroupEditor } from "./group-editor";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, FileText, GitBranch, LoaderCircle, MapPin, RefreshCw, ShieldCheck, X, XCircle } from "lucide-react";
import { api, date, number, shortId } from "@/lib/api";
import { AnalysisGroup, AnalysisRun, GroupEvidence, scoreLabel } from "@/lib/analysis";
import { ReviewedGroup, useResource } from "@/lib/workspace";
import { Empty, ErrorBox, Loading, PageTitle, PrivacyBadge } from "@/components/ui";
import { ReviewBadge } from "@/components/workspace-ui";

type Decision = "confirmed" | "rejected" | "proposed";
function ReviewDialog({ group, decision, close, saved }: { group: ReviewedGroup; decision: Decision; close: () => void; saved: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const title = decision === "confirmed" ? "Подтвердить объединение?" : decision === "rejected" ? "Отклонить группу?" : "Вернуть на проверку?";
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  async function save() {
    setBusy(true); setError("");
    try {
      await api(`/groups/${group.id}/review`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: decision, version: group.version, reason: reason.trim() }) });
      saved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить решение."); }
    finally { setBusy(false); }
  }
  return <dialog ref={ref} className="appeal-dialog decision-dialog" aria-labelledby="decision-title" onCancel={event => { event.preventDefault(); if (!busy) close(); }}><div className="dialog-content"><div className="dialog-heading"><h2 id="decision-title">{title}</h2><button className="icon-button" aria-label="Закрыть подтверждение" disabled={busy} onClick={close}><X size={19} /></button></div><p className="decision-copy">{decision === "confirmed" ? "Подтверждается состав группы, а не причина аварии. Убедитесь, что территория, даты и тексты согласуются." : "Решение изменит статус группы. Подтверждающие обращения и история сохранятся."}</p><label className="field"><span>Основание решения *</span><textarea autoFocus rows={4} maxLength={500} disabled={busy} value={reason} onChange={event => setReason(event.target.value)} placeholder="Опишите, какие признаки подтверждают ваше решение. Без персональных сведений." /></label>{error && <ErrorBox message={error} />}<div className="dialog-actions"><button className="button button-white" onClick={close} disabled={busy}>Отмена</button><button className={`button ${decision === "rejected" ? "button-danger" : "button-primary"}`} disabled={busy || reason.trim().length < 3} onClick={save}>{busy && <LoaderCircle size={16} className="spin" />}Сохранить решение</button></div></div></dialog>;
}

function Evidence({ groupId }: { groupId: string }) {
  const { data, loading, error, reload } = useResource<GroupEvidence[]>(`/groups/${groupId}/appeals`);
  if (loading) return <Loading label="Загружаем подтверждающие обращения…" />;
  if (error) return <ErrorBox message={error} retry={reload} />;
  return <div className="detail-evidence-list">{data?.map(item => {
    const snapshot = item.analysis;
    const changed = !!snapshot && item.appeal_version !== snapshot.input_version;
    return <article className="detail-evidence" key={item.id}><div className="detail-evidence-top"><span className="file-icon"><FileText size={19} /></span><div><strong>{item.source_record_id}</strong><small>{snapshot?.source || item.source} · {date(snapshot?.date || item.date)}</small></div><PrivacyBadge status={snapshot?.privacy_status || item.privacy_status} /></div><p>{snapshot?.text ?? item.text}</p><div className="detail-evidence-bottom"><span><MapPin size={13} />{(snapshot ? snapshot.address : item.address) || "Адрес неизвестен"}</span><Link href={`/appeals?q=${encodeURIComponent(item.source_record_id)}`}>В реестр <ArrowRight size={14} /></Link></div>{snapshot?.duplicate_kind === "republication_candidate" && <p className="evidence-stale">Предполагаемая копия обращения {snapshot.duplicate_of}. Дополнительным независимым свидетельством не считается.</p>}{changed && <p className="evidence-stale">Текст изменился после анализа. Здесь показан сохранённый снимок запуска.</p>}<code className="evidence-id">ID: {item.id}</code></article>;
  })}</div>;
}

function RelatedCase({ id }: { id: string }) {
  const { data, error } = useResource<AnalysisGroup>(`/groups/${id}`);
  return <Link className="related-case" href={`/problems/${id}`}><GitBranch size={18} /><span><strong>{data?.category || `Случай #${shortId(id)}`}</strong><small>{error ? "Откройте для повторной загрузки" : data ? `${date(data.start_date)} — ${date(data.end_date)}` : "Загрузка…"}</small></span><ArrowRight size={15} /></Link>;
}

export function ProblemDetail({ id }: { id: string }) {
  const { data: group, loading, error, reload } = useResource<ReviewedGroup>(`/groups/${encodeURIComponent(id)}`);
  const { data: runs } = useResource<AnalysisRun[]>("/analysis/runs");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [notice, setNotice] = useState(false);
  const latest = runs?.find(run => run.status === "completed");
  const editable = !!group && group.status !== "archived" && !group.stale && latest?.id === group.run_id;
  return <><Link className="back-link" href="/problems"><ArrowLeft size={16} />Все группы</Link>
    {loading ? <Loading /> : error ? <ErrorBox message={error} retry={reload} /> : !group ? <Empty title="Группа не найдена" description="Откройте список групп и выберите сохранённый результат." /> : <>
      <PageTitle eyebrow={`${group.kind === "case" ? "ЛОКАЛЬНЫЙ СЛУЧАЙ" : "ПОВТОРЯЮЩАЯСЯ ПРОБЛЕМА"} · #${shortId(group.id)}`} title={group.title || group.category} description={group.territory || "Территория не определена"}><ReviewBadge status={group.status} /><button className="button button-white button-icon" aria-label="Обновить карточку группы" onClick={reload}><RefreshCw size={16} /></button></PageTitle>
      {group.merged_into && <p className="scope-strip">Группа объединена. <Link href={`/problems/${group.merged_into}`}>Открыть текущую группу</Link></p>}{notice && <div className="success-notice" role="status"><CheckCircle2 size={18} />Решение сохранено в истории группы.</div>}
      {!editable && <div className="scope-strip scope-stale"><AlertTriangle size={18} /><p>{!runs ? "Проверяем актуальность запуска…" : "Показан исторический или устаревший состав. Для нового решения откройте актуальные группы после анализа."}</p><Link href="/analysis">К анализу <ArrowRight size={14} /></Link></div>}
      <div className="detail-layout"><div className="detail-main"><section className="panel detail-section"><h2>Картина события</h2><p className="detail-lead">{group.kind === "case" ? (group.message_count === 1 ? "Сохранено отдельное сообщение. Других подтверждений в этой группе нет." : "Сообщения предложены как один локальный случай в близком месте и времени.") : "Связаны отдельные случаи из разных периодов на одной территории."} Причина события системой не устанавливается.</p><div className="detail-stat-grid"><div><span>Обращения</span><strong>{number(group.message_count)}</strong></div><div><span>Источники</span><strong>{number(group.source_count)}</strong></div><div><span>Публикации без копий*</span><strong>{number(group.independent_evidence_count)}</strong></div></div><div className="detail-period"><span>Даты обращений</span><strong>{date(group.start_date)} — {date(group.end_date)}</strong></div></section>
        <section className="panel detail-section"><h2><ShieldCheck size={19} />Почему обращения связаны</h2><ul className="reason-list">{group.explanations.map((reason, index) => <li key={index}><CheckCircle2 size={16} /><span>{reason}</span></li>)}</ul><div className="similarity-note">{group.explanation_stale ? "Основание AI устарело после ручной правки. Текущий состав проверяет аналитик." : group.message_count > 1 ? <>Минимальное попарное сходство: <strong>{scoreLabel(group.minimum_similarity)}</strong>. Это оценка метода, не вероятность общей аварии.</> : "Попарное сходство не применяется к одному сообщению."}</div></section>
        <section className="panel detail-section uncertainty-section"><h2><AlertTriangle size={19} />Что требует проверки</h2>{group.uncertainties.length ? <ul>{group.uncertainties.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="panel-help">Дополнительных факторов неопределённости не отмечено. Основания всё равно требуют проверки аналитиком.</p>}</section>
        <section className="panel detail-section"><div className="detail-section-heading"><h2><FileText size={19} />Подтверждающие обращения</h2><span className="badge badge-blue">{number(group.message_count)}</span></div><Evidence key={`${id}:${group.version}`} groupId={id} /></section>
      </div><aside className="detail-sidebar"><section className="panel detail-section"><h2>Решение аналитика</h2><p className="panel-help">Проверьте тексты, место и период. Решение сохраняется с вашим комментарием.</p><div className="analyst-actions"><button className="button button-primary" disabled={!editable || group.status === "confirmed"} onClick={() => setDecision("confirmed")}><CheckCircle2 size={16} />Подтвердить объединение</button><button className="button button-white danger-text" disabled={!editable || group.status === "rejected"} onClick={() => setDecision("rejected")}><XCircle size={16} />Отклонить группу</button>{group.status !== "proposed" && <button className="button button-white" disabled={!editable} onClick={() => setDecision("proposed")}><RefreshCw size={16} />Вернуть на проверку</button>}</div><GroupEditor group={group} disabled={!editable} saved={() => { setNotice(true); reload(); }} /></section>
        <section className="panel detail-section"><h2>Связанные случаи</h2>{group.case_ids?.length ? group.case_ids.map(caseId => <RelatedCase key={`${caseId}:${group.version}`} id={caseId} />) : <p className="panel-help">Это отдельный случай. Связь с повторяющейся проблемой не установлена.</p>}</section>
        <section className="panel detail-section"><h2>История решений</h2>{group.review_history?.length ? <ol className="review-timeline">{[...group.review_history].reverse().map(event => <li key={event.version}><ReviewBadge status={event.status} /><p>{event.action ? ({ review: "Решение", edit: "Описание", add: "Добавление", remove: "Исключение", split: "Разделение", merge: "Объединение" } as Record<string, string>)[event.action] || "Обновление связей" : "Решение"}: {event.reason}</p><small>{new Date(event.created_at).toLocaleString("ru-RU")} · версия {event.version} · {event.actor === "demo_operator" ? "Демо-оператор" : "Локальный оператор (прежняя запись)"}</small>{event.old_value && <details><summary>До и после</summary><pre className="audit-values">{JSON.stringify({ "До": event.old_value, "После": event.new_value }, null, 2)}</pre></details>}</li>)}</ol> : <p className="panel-help">Ручных решений ещё нет. Группа предложена системой.</p>}</section></aside></div>
      <p className="dashboard-footnote">* Количество публикаций без предполагаемых копий не устанавливает независимость авторов или число жителей. ID группы: {group.id}.</p>
      {decision && <ReviewDialog group={group} decision={decision} close={() => setDecision(null)} saved={() => { setDecision(null); setNotice(true); reload(); }} />}
    </>}
  </>;
}
