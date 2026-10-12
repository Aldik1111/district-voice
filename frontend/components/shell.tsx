"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, ChevronRight, Database, FileInput, FileBarChart2, GitBranch, LayoutDashboard, ListFilter, Menu, Radio, ShieldCheck, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";

const navigation = [
  { href: "/", label: "Обзор", icon: LayoutDashboard },
  { href: "/import", label: "Загрузка данных", icon: FileInput },
  { href: "/appeals", label: "Все обращения", icon: ListFilter },
  { href: "/analysis", label: "AI-анализ", icon: Sparkles },
  { href: "/problems", label: "Системные проблемы", icon: GitBranch },
  { href: "/reports", label: "Отчёты", icon: FileBarChart2 },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    const check = () => api<{ status: string; database: string }>("/health").then(data => { if (live) setConnected(data.status === "ok" && data.database === "ok"); }).catch(() => { if (live) setConnected(false); });
    void check();
    const timer = setInterval(check, 30000);
    return () => { live = false; clearInterval(timer); };
  }, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  const active = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(href + "/"));
  const current = navigation.find(item => active(item.href));
  return <div className="app-shell">
    {open && <button aria-label="Закрыть меню" className="sidebar-backdrop" onClick={() => setOpen(false)} />}
    <aside id="main-navigation" className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <Link href="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark"><Radio size={24} strokeWidth={2.5} /></span><span><strong>Голос района</strong><small>Платформа обращений</small></span></Link>
      <div className="workspace"><span className="workspace-icon"><Building2 size={18} /></span><div><strong>Рабочее пространство</strong><span>Локальная среда</span></div><span className="workspace-dot" /></div>
      <p className="nav-label">РАБОТА С ДАННЫМИ</p>
      <nav aria-label="Основная навигация">{navigation.map(({ href, label, icon: Icon }) => <Link href={href} key={href} onClick={() => setOpen(false)} className={`nav-link ${active(href) ? "active" : ""}`} aria-current={active(href) ? "page" : undefined}><Icon size={19} /><span>{label}</span>{active(href) && <ChevronRight size={15} className="nav-chevron" />}</Link>)}</nav>
      <div className="next-stage"><div className="next-stage-title"><ShieldCheck size={17} />Решение за аналитиком</div><p>Проверяйте основания объединения, территории и даты. Алгоритм предлагает, вы оцениваете.</p><Link className="text-button" href="/problems" onClick={() => setOpen(false)}>Открыть результаты <ChevronRight size={13} /></Link></div>
      <div className="sidebar-bottom"><ShieldCheck size={18} /><div><strong>Данные на вашем устройстве</strong><p>Без облачных AI-сервисов</p></div></div>
      <div className="user-card"><div className="avatar">А</div><div><strong>Демо-оператор</strong><span>Локально · без авторизации</span></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-menu" aria-expanded={open} aria-controls="main-navigation" aria-label={open ? "Закрыть меню" : "Открыть меню"} onClick={() => setOpen(!open)}>{open ? <X size={20} /> : <Menu size={20} />}</button><span>Рабочее пространство</span><ChevronRight size={13} /><strong>{current?.label || "Обзор"}</strong></div><div className={`connection ${connected === false ? "connection-off" : ""}`} title="Состояние FastAPI и базы SQLite"><span className={`status-dot ${connected === null ? "status-pending" : ""}`} /><span>{connected === null ? "Подключение…" : connected ? "Система доступна" : "Сервер недоступен"}</span><Database size={14} /></div></header>
      <main className="main-content"><div className="synthetic-banner">Демонстрационный режим · набор «ДЕМО» содержит синтетические обращения, не сообщения жителей.</div>{children}</main>
      <footer className="footer"><span>Голос района · Казахстан</span><span>Локальная аналитика обращений · MVP</span></footer>
    </div>
  </div>;
}
