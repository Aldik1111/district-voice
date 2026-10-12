"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Download, FilePenLine, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { api, date, number, shortId } from "@/lib/api";
import { AnalysisGroup } from "@/lib/analysis";
import { useResource } from "@/lib/workspace";
import { Empty, ErrorBox, Loading, PageTitle } from "./ui";

type Options = { start: string | null; end: string | null; territories: string[] };
type Scope = { start: string; end: string; territory: string | null };
type Snapshot = { scope: Scope; total_messages: number; unique_messages: number; confirmed_groups: number; confirmed_problems: number; blocked_messages: number; synthetic_messages: number; categories: Record<string, number>; territories: Record<string, number>; sources: Record<string, number>; groups: (AnalysisGroup & { scope_clipped: boolean })[]; counting_note: string };
type Summary = { id: string; series_id: string; version: number; revision: number; status: string; title: string; body: string; scope: Scope; snapshot: Snapshot; checksum: string; approved_at: string | null; created_at: string; actor: string };

function SnapshotView({ snapshot }: { snapshot: Snapshot }) {
  return <>
    <div className="report-metrics"><div><span>Всего сообщений</span><strong>{number(snapshot.total_messages)}</strong></div><div><span>Уникальных публикаций</span><strong>{number(snapshot.unique_messages)}</strong></div><div><span>Подтверждено групп</span><strong>{number(snapshot.confirmed_groups)}</strong></div><div><span>Повторяющихся проблем</span><strong>{number(snapshot.confirmed_problems)}</strong></div></div>
    {snapshot.synthetic_messages > 0 && <p className="synthetic-banner">Демонстрационные данные: {number(snapshot.synthetic_messages)} синтетических сообщений в этом срезе.</p>}
    <p className="panel-help">{snapshot.counting_note}</p>
    <div className="summary-breakdowns">{[["Категории", snapshot.categories], ["Территории", snapshot.territories], ["Источники", snapshot.sources]].map(([label, values]) => <section key={label as string}><h3>{label as string}</h3>{Object.entries(values).map(([name, count]) => <div className="summary-breakdown-row" key={name}><span>{name}</span><strong>{count}</strong></div>)}</section>)}</div>
    <section className="report-section"><h3>Подтверждённые проблемы и случаи</h3>{snapshot.groups.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Группа</th><th>Территория / период</th><th>Обращения / источники</th><th>Подтверждающие ID</th></tr></thead><tbody>{snapshot.groups.map(group => <tr key={group.id}><td><Link className="table-title-link" href={`/problems/${group.id}`}>{group.title || group.category}</Link><small>{group.kind === "case" ? "Случай" : "Повторяющаяся проблема"} · v{group.version}</small><span className="badge badge-green">Подтверждена</span></td><td>{group.territory || "Территория неизвестна"}<small>{date(group.start_date)} — {date(group.end_date)}</small>{group.scope_clipped && <small>Часть группы в выбранном срезе</small>}</td><td>{group.message_count} / {group.source_count}</td><td><details><summary>{group.appeal_ids.length} ID</summary>{group.appeal_ids.map(id => <code className="evidence-id" key={id}>{id}</code>)}</details></td></tr>)}</tbody></table></div> : <Empty title="Нет подтверждённых групп" description="Откройте системные проблемы и сохраните решение аналитика. После этого пересчитайте показатели." action={<Link className="button button-white" href="/problems">Проверить группы</Link>} />}</section>
  </>;
}

function Workflow({ options }: { options: Options }) {
  const [scope, setScope] = useState<Scope>({ start: options.start || "", end: options.end || "", territory: null });
  const [preview, setPreview] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<Summary | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const history = useResource<Summary[]>("/summaries");
  const approval = useRef<HTMLDialogElement>(null);
  const dirty = !!selected && (title !== selected.title || body !== selected.body);
  const approved = selected?.status === "approved";
  function pick(item: Summary) { setSelected(item); setTitle(item.title); setBody(item.body); setPreview(null); }
  async function perform(name: string, operation: () => Promise<void>) {
    setBusy(name); setError(""); setNotice("");
    try { await operation(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выполнить действие."); } finally { setBusy(""); }
  }
  const calculate = () => perform("calculate", async () => { const data = await api<Snapshot>("/summaries/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scope) }); setPreview(data); setSelected(null); });
  const create = (previous?: Summary) => perform("create", async () => {
    const item = await api<Summary>("/summaries", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...(previous?.scope || scope), title: previous?.title || "Аналитическая сводка", ...(previous ? { previous_id: previous.id } : {}) }) });
    pick(item); history.reload(); setNotice("Черновик сохранён в SQLite. Проверьте текст и рассчитанные показатели.");
  });
  const save = () => selected && perform("save", async () => { pick(await api<Summary>(`/summaries/${selected.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision: selected.revision, title, body }) })); history.reload(); setNotice("Текст черновика сохранён."); });
  const approve = () => selected && perform("approve", async () => { pick(await api<Summary>(`/summaries/${selected.id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision: selected.revision }) })); approval.current?.close(); history.reload(); setNotice("Версия утверждена. Снимок защищён от изменения, экспорт готов."); });
  const download = (format: string) => selected && perform("export", async () => {
    const current = await api<Summary>(`/summaries/${selected.id}`);
    if (current.status !== "approved") throw new Error("Сначала утвердите версию.");
    const link = document.createElement("a"); link.href = `/api/summaries/${current.id}/export/${format}`; link.download = `district-voice-summary-v${current.version}.${format}`; document.body.appendChild(link); link.click(); link.remove(); setNotice("Экспорт утверждённой версии передан браузеру для сохранения.");
  });
  return <>
    <section className="panel summary-filter"><div className="panel-heading"><div><h2>Период и территория</h2><p>Показатели рассчитываются по текущему анализу в SQLite.</p></div><span className="badge badge-blue">Демо-оператор</span></div><div className="summary-filter-grid"><label className="field"><span>Начало периода</span><input type="date" value={scope.start} onChange={event => { setScope({ ...scope, start: event.target.value }); setPreview(null); }} /></label><label className="field"><span>Конец периода</span><input type="date" value={scope.end} onChange={event => { setScope({ ...scope, end: event.target.value }); setPreview(null); }} /></label><label className="field"><span>Территория</span><select value={scope.territory || ""} onChange={event => { setScope({ ...scope, territory: event.target.value || null }); setPreview(null); }}><option value="">Все территории</option>{options.territories.map(item => <option key={item}>{item}</option>)}</select></label><button className="button button-primary" disabled={!!busy || !scope.start || !scope.end || scope.start > scope.end || dirty} onClick={calculate}>{busy === "calculate" ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}Рассчитать показатели</button></div>{dirty && <p className="small-print">Сохраните правки текста перед переключением среза или версии.</p>}</section>
    {error && <ErrorBox message={error} />}{notice && <div className="success-notice" role="status"><CheckCircle2 size={18} />{notice}</div>}
    {preview && <section className="panel report-document"><div className="panel-heading"><div><h2>Предпросмотр сводки</h2><p>{date(preview.scope.start)} — {date(preview.scope.end)} · {preview.scope.territory || "Все территории"}</p></div><button className="button button-primary" disabled={!!busy || !preview.total_messages} onClick={() => create()}><FilePenLine size={16} />Создать черновик</button></div><SnapshotView snapshot={preview} /></section>}
    {selected && <article className="panel report-document"><div className="report-document-heading"><ShieldCheck size={30} /><div><p className="section-kicker">СВОДКА · ВЕРСИЯ {selected.version}</p><h2>{approved ? selected.title : "Редактор черновика"}</h2><p>{date(selected.scope.start)} — {date(selected.scope.end)} · {selected.scope.territory || "Все территории"}</p></div><span className={`badge ${approved ? "badge-green" : "badge-amber"}`}>{approved ? "Утверждена" : "Черновик"}</span></div>
      {approved ? <><p className="summary-body">{selected.body}</p><div className="approved-stamp"><ShieldCheck size={18} /><div><strong>Снимок зафиксирован · демо-оператор</strong><small>{new Date(selected.approved_at!).toLocaleString("ru-RU")} · ID {selected.id}</small><code>SHA256: {selected.checksum}</code></div></div></> : <><label className="field"><span>Название сводки</span><input maxLength={160} value={title} onChange={event => setTitle(event.target.value)} /></label><label className="field"><span>Текст аналитика</span><textarea rows={6} maxLength={10000} value={body} onChange={event => setBody(event.target.value)} /></label><p className="small-print">Не добавляйте неподтверждённые причины и персональные данные. Показатели ниже вычисляются отдельно и не редактируются в тексте.</p></>}
      <div className="summary-buttons">{approved ? <><button className="button button-primary" disabled={!!busy} onClick={() => download("csv")}><Download size={16} />Экспорт CSV</button><button className="button button-white" disabled={!!busy} onClick={() => download("xlsx")}><Download size={16} />Экспорт XLSX</button></> : <><button className="button button-white" disabled={!!busy || !dirty || title.trim().length < 3 || body.trim().length < 3} onClick={save}>Сохранить текст</button><button className="button button-primary" disabled={!!busy || dirty || !selected.snapshot.confirmed_groups} onClick={() => approval.current?.showModal()}><ShieldCheck size={16} />Утвердить версию</button></>}<button className="button button-white" disabled={!!busy || dirty} onClick={() => create(selected)}>Создать новую версию</button>{busy && <LoaderCircle size={19} className="spin" />}</div>
      <SnapshotView snapshot={selected.snapshot} />
    </article>}
    {!preview && !selected && <section className="panel"><Empty title="Подготовьте аналитическую сводку" description="Выберите период и территорию, рассчитайте показатели, затем создайте черновик. Утверждённые версии доступны в истории ниже." /></section>}
    <section className="panel detail-section"><h2>Сохранённые версии</h2>{history.loading ? <Loading /> : history.error ? <ErrorBox message={history.error} retry={history.reload} /> : history.data?.length ? <div className="summary-history">{history.data.map(item => <button className={`summary-history-item ${selected?.id === item.id ? "selected" : ""}`} key={item.id} disabled={!!busy || dirty} onClick={() => perform("open", async () => pick(await api<Summary>(`/summaries/${item.id}`)))}><span><strong>{item.title} · v{item.version}</strong><small>{date(item.created_at)} · #{shortId(item.id)} · {item.scope.territory || "Все территории"}</small></span><span className={`badge ${item.status === "approved" ? "badge-green" : "badge-amber"}`}>{item.status === "approved" ? "Утверждена" : "Черновик"}</span></button>)}</div> : <p className="panel-help">Сохранённых сводок пока нет.</p>}</section>
    <dialog className="appeal-dialog" ref={approval} onCancel={event => { if (busy) event.preventDefault(); }}><div className="dialog-content"><h2>Утвердить версию {selected?.version}?</h2><p>Текст, показатели, подтверждённые группы и ID станут неизменяемым снимком. Для последующих правок потребуется новая версия. Подпись: демо-оператор.</p>{error && <ErrorBox message={error} />}<div className="dialog-actions"><button className="button button-white" disabled={!!busy} onClick={() => approval.current?.close()}>Отмена</button><button className="button button-primary" disabled={!!busy} onClick={approve}>{busy === "approve" && <LoaderCircle size={16} className="spin" />}Подтвердить утверждение</button></div></div></dialog>
  </>;
}

export function SummaryWorkflow() {
  const options = useResource<Options>("/summaries/options");
  return <><PageTitle eyebrow="ОТ ДАННЫХ К РЕШЕНИЮ" title="Отчёты" description="Рассчитайте показатели, проверьте текст и утвердите неизменяемую версию сводки." />{options.loading ? <Loading /> : options.error ? <ErrorBox message={options.error} retry={options.reload} /> : options.data && <Workflow options={options.data} />}</>;
}
