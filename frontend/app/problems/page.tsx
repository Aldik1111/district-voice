"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft, ChevronRight, Grid2X2, List, RefreshCw, Search, X } from "lucide-react";
import { date, number } from "@/lib/api";
import { AnalysisGroup, AnalysisRun } from "@/lib/analysis";
import { DashboardData, useResource } from "@/lib/workspace";
import { Empty, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { GroupCard, ReviewBadge, RunScope } from "@/components/workspace-ui";

function GroupCollection({ run }: { run: AnalysisRun }) {
  const { data: groups, loading, error, reload } = useResource<AnalysisGroup[]>(`/groups?run_id=${run.id}`);
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [page, setPage] = useState(1);
  const filtered = (groups || []).filter(group => (!kind || group.kind === kind) && (!status || group.status === status) && `${group.title || ""} ${group.category} ${group.territory || ""} ${group.id}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  const visible = filtered.slice((page - 1) * 12, page * 12);
  const reset = () => { setKind(""); setStatus(""); setQuery(""); setPage(1); };
  return <>
    <div className="group-controls"><div className="segmented" aria-label="Вид группы">{[["", "Все группы"], ["problem", "Повторяющиеся"], ["case", "Локальные случаи"]].map(([value, label]) => <button key={value} className={kind === value ? "selected" : ""} aria-pressed={kind === value} onClick={() => { setKind(value); setPage(1); }}>{label}</button>)}</div><div className="view-switch" aria-label="Представление групп"><button aria-label="Карточки" aria-pressed={view === "cards"} onClick={() => setView("cards")}><Grid2X2 size={17} /></button><button aria-label="Таблица" aria-pressed={view === "table"} onClick={() => setView("table")}><List size={18} /></button></div></div>
    <div className="group-filters"><label className="search-field"><Search size={17} /><input aria-label="Поиск групп" placeholder="Категория, территория или ID группы" value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} />{query && <button className="icon-button" aria-label="Очистить поиск групп" onClick={() => { setQuery(""); setPage(1); }}><X size={14} /></button>}</label><select className="standalone-select" aria-label="Статус группы" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">Все статусы</option><option value="proposed">Ожидают проверки</option><option value="confirmed">Подтверждены</option><option value="rejected">Отклонены</option></select><button className="button button-white button-icon" aria-label="Обновить группы" onClick={reload}><RefreshCw size={16} /></button></div>
    {error ? <ErrorBox message={error} retry={reload} /> : loading ? <Loading label="Загружаем группы и связи…" /> : !filtered.length ? <section className="panel"><Empty title={kind === "problem" ? "Повторяющихся проблем не найдено" : "Групп по этим условиям нет"} description="Повторяющаяся проблема связывает случаи из разных периодов. Один случай сохраняется отдельно." action={<button className="button button-white" onClick={reset}>Показать все группы</button>} /></section> : view === "cards" ? <div className="problem-grid">{visible.map(group => <GroupCard group={group} key={group.id} />)}</div> : <section className="panel table-scroll"><table className="data-table groups-table"><thead><tr><th>Проблема / категория</th><th>Территория</th><th>Период</th><th>Обращения</th><th>Источники</th><th>Проверка</th><th /></tr></thead><tbody>{visible.map(group => <tr key={group.id}><td><Link className="table-title-link" href={`/problems/${group.id}`}>{group.title || group.category}</Link><small>{group.kind === "case" ? "Локальный случай" : "Повторяющаяся проблема"}</small></td><td>{group.territory || "Неизвестна"}</td><td className="date-cell">{date(group.start_date)}<small>{date(group.end_date)}</small></td><td>{number(group.message_count)}</td><td>{number(group.source_count)}</td><td><ReviewBadge status={group.status} /></td><td><Link className="icon-button" href={`/problems/${group.id}`} aria-label={`Подробнее о группе ${group.category} ${group.territory || "без адреса"}`}><ArrowRight size={17} /></Link></td></tr>)}</tbody></table></section>}
    {filtered.length > 12 && <div className="table-footer group-pagination"><span>Страница {page}</span><div className="pagination"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={15} />Назад</button><button disabled={page * 12 >= filtered.length} onClick={() => setPage(value => value + 1)}>Вперёд<ChevronRight size={15} /></button></div></div>}
    <p className="dashboard-footnote">* «Без копий» — количество сообщений, не помеченных как предполагаемые перепубликации. Это не подтверждает независимость авторов. Каждая группа содержит реальные ссылки на обращения.</p>
  </>;
}

export default function ProblemsPage() {
  const { data, loading, error, reload } = useResource<DashboardData>("/dashboard");
  return <><PageTitle eyebrow="ОТ СООБЩЕНИЙ К ПРИЧИНАМ ДЛЯ ПРОВЕРКИ" title="Системные проблемы" description="Связанные обращения, локальные случаи и повторения. Проверяйте каждое объединение."><Link className="button button-primary" href="/analysis">К AI-анализу <ArrowRight size={16} /></Link></PageTitle>
    {error ? <ErrorBox message={error} retry={reload} /> : loading ? <Loading /> : <><div className="group-summary"><span><strong>{number(data?.case_count || 0)}</strong> локальных случаев</span><span><strong>{number(data?.problem_count || 0)}</strong> повторяющихся проблем</span><span><strong>{number(data?.pending_review || 0)}</strong> ожидают проверки</span><span><strong>{number(data?.confirmed_groups || 0)}</strong> подтверждено</span></div><RunScope run={data?.run} />{data?.run ? <GroupCollection key={data.run.id} run={data.run} /> : <section className="panel"><Empty title="Группы появятся после анализа" description="Сначала загрузите обращения и запустите локальный анализ. Система предложит связи для проверки." action={<Link className="button button-primary" href="/analysis">Запустить анализ <ArrowRight size={15} /></Link>} /></section>}</>}
  </>;
}
