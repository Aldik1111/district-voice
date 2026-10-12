"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarDays, CheckCircle2, ClipboardCheck, FileText, Fingerprint, GitBranch, Layers3, MapPin, RefreshCw, X } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { date, number } from "@/lib/api";
import { DashboardData, useResource } from "@/lib/workspace";
import { Empty, ErrorBox, ImportLink, Loading, PageTitle } from "@/components/ui";
import { ReviewBadge, RunButton, RunScope } from "@/components/workspace-ui";

const colors = ["#2563eb", "#67a1fa", "#0d9488", "#8b7dd8", "#f0b955", "#94a3b8", "#38bdf8", "#a3bded", "#64748b", "#cbd5e1"];

export default function Dashboard() {
  const { data, loading, error, reload } = useResource<DashboardData>("/dashboard");
  const [notice, setNotice] = useState(false);
  const metrics = [
    { title: "Всего обращений", value: data?.total_appeals, note: "Сохранено в реестре", icon: FileText, tone: "blue" },
    { title: "Уникальных обращений", value: data?.unique_appeals, note: data?.run ? "Без предполагаемых перепубликаций*" : "Будет определено после анализа", icon: Fingerprint, tone: "green" },
    { title: "Найденных групп", value: data?.groups_count, note: data?.run ? `${number(data.case_count)} случаев · ${number(data.problem_count)} повторяющихся` : "После первого запуска анализа", icon: Layers3, tone: "violet" },
    { title: "Ожидают проверки", value: data?.pending_review, note: "Группы без решения аналитика", icon: ClipboardCheck, tone: "amber" },
  ];
  return <>
    <PageTitle eyebrow="АНАЛИТИЧЕСКОЕ ПРОСТРАНСТВО" title="Пульс вашего района" description="Обращения, связанные события и решения — в одной картине.">
      <button className="button button-white button-icon" aria-label="Обновить обзор" onClick={reload} disabled={loading}><RefreshCw size={17} className={loading ? "spin" : ""} /></button>
      <RunButton disabled={!data?.total_appeals} completed={() => { reload(); setNotice(true); }} />
    </PageTitle>
    {error && <ErrorBox message={error} retry={reload} />}
    {notice && <div className="success-notice" role="status"><CheckCircle2 size={18} />Анализ завершён. Показатели обновлены.<button className="icon-button" aria-label="Скрыть уведомление" onClick={() => setNotice(false)}><X size={16} /></button></div>}
    <div className="dashboard-context"><span className="section-kicker">ОБРАЩЕНИЯ И РЕЗУЛЬТАТЫ</span><span><CalendarDays size={14} />{data?.period ? `${date(data.period.start)} — ${date(data.period.end)}` : "Период появится после загрузки"}</span></div>
    <section className="metric-grid" aria-label="Ключевые показатели">{metrics.map(({ title, value, note, icon: Icon, tone }) => <div className="metric-card" key={title}><div className="metric-top"><span>{title}</span><span className={`metric-icon ${tone}`}><Icon size={20} /></span></div><strong className={`metric-value ${loading ? "metric-loading" : ""}`}>{value == null ? "—" : number(value)}</strong><span className="metric-description">{note}</span></div>)}</section>
    <RunScope run={data?.run} />
    <div className="dashboard-visuals">
      <section className="panel"><div className="panel-heading"><div><h2>Динамика обращений</h2><p>Количество по дате обращения · весь реестр</p></div><span className="chart-legend"><i />Обращения</span></div>
        {loading ? <Loading /> : data?.by_date.length ? <div className="chart-wrapper"><ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 600, height: 270 }}><AreaChart data={data.by_date} margin={{ top: 8, right: 18, left: -18, bottom: 8 }}><defs><linearGradient id="volume-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.22} /><stop offset="100%" stopColor="#3b82f6" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9eef5" strokeDasharray="4 4" /><XAxis dataKey="date" tickFormatter={value => new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} dy={8} minTickGap={24} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#64748b" }} /><Tooltip labelFormatter={value => date(String(value))} formatter={value => [number(Number(value)), "Обращения"]} contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 13 }} /><Area type="monotone" dataKey="count" name="Обращения" stroke="#2563eb" strokeWidth={2.5} fill="url(#volume-fill)" dot={{ r: 3, fill: "white", strokeWidth: 2 }} activeDot={{ r: 5 }} /></AreaChart></ResponsiveContainer></div> : <Empty title="Пока нет данных для графика" description="Загрузите обращения с датами — динамика появится автоматически." action={<ImportLink />} />}
      </section>
      <section className="panel"><div className="panel-heading"><div><h2>Темы обращений</h2><p>Категории последнего успешного анализа</p></div></div>
        {loading ? <Loading /> : data?.by_category.length ? <div className="category-distribution"><div className="donut-chart"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 230, height: 210 }}><PieChart><Pie data={data.by_category} dataKey="count" nameKey="name" innerRadius={65} outerRadius={87} paddingAngle={3} stroke="none">{data.by_category.map((item, index) => <Cell key={item.name} fill={colors[index % colors.length]} />)}</Pie><Tooltip formatter={value => [number(Number(value)), "Обращения"]} contentStyle={{ borderRadius: 10, fontSize: 12 }} /></PieChart></ResponsiveContainer><div className="donut-total"><strong>{number(data.analyzed)}</strong><span>обработано</span></div></div><div className="category-legend">{data.by_category.map((item, index) => <div key={item.name}><i style={{ background: colors[index % colors.length] }} /><span>{item.name}</span><strong>{number(item.count)}</strong><small>{item.percent}%</small></div>)}</div></div> : <Empty title="Категории ещё не определены" description="Запустите AI-анализ, чтобы увидеть распределение тем." action={<Link className="text-button" href="/analysis">Перейти к анализу <ArrowRight size={15} /></Link>} />}
      </section>
    </div>
    <div className="dashboard-bottom-grid">
      <section className="panel territory-panel"><div className="panel-heading"><div><h2>Территории в фокусе</h2><p>{data?.run ? "По обработанным обращениям" : "По адресам из реестра"}</p></div><MapPin size={19} className="muted" /></div>
        {loading ? <Loading /> : data?.by_territory.length ? <div className="territory-rankings">{data.by_territory.map((item, index) => <div className="territory-rank" key={item.name}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><div><div><span>{item.name}</span><strong>{number(item.count)}</strong></div><div className="rank-track"><span style={{ width: `${item.percent}%` }} /></div></div></div>)}</div> : <Empty title="Территорий пока нет" description="Адреса берутся из обращений. Неизвестные адреса не додумываются." />}
      </section>
      <section className="panel"><div className="panel-heading"><div><h2>Последние системные проблемы</h2><p>Повторяющиеся события в одной территории</p></div><Link href="/problems" className="text-button">Все группы <ArrowRight size={15} /></Link></div>
        {loading ? <Loading /> : data?.latest_problems.length ? <div className="latest-group-list">{data.latest_problems.map(group => <Link className="latest-group" href={`/problems/${group.id}`} key={group.id}><span className="category-icon"><GitBranch size={20} /></span><div><strong>{group.category}</strong><p>{group.territory || "Территория неизвестна"} · {number(group.message_count)} обращений</p><ReviewBadge status={group.status} /></div><ArrowRight size={17} /></Link>)}</div> : <div className="recurrence-empty"><span className="empty-icon"><GitBranch size={25} /></span><div><h3>{data?.run ? "Повторяющихся проблем не найдено" : "Сначала проанализируйте обращения"}</h3><p>{data?.run ? "Один локальный случай ещё не означает системную проблему. Проверьте найденные группы ниже." : "Здесь появятся связанные случаи из разных периодов."}</p></div></div>}
        {!!data?.latest_groups.length && <div className="latest-cases"><p className="section-kicker">ПОСЛЕДНИЕ НАЙДЕННЫЕ ГРУППЫ</p>{data.latest_groups.slice(0, 3).map(group => <Link href={`/problems/${group.id}`} key={group.id}><span><strong>{group.category}</strong><small>{group.territory || "Территория неизвестна"}</small></span><span className="badge badge-neutral">{number(group.message_count)} обращ.</span><ArrowRight size={15} /></Link>)}</div>}
      </section>
    </div>
    <p className="dashboard-footnote">* Уникальность здесь — оценка числа публикаций без предполагаемых копий в выбранном анализе. Это не число жителей и не подтверждение независимости авторов. Данные и расчёты поступают из локальной базы.</p>
  </>;
}
