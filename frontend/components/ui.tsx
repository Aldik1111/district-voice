"use client";

import { AlertCircle, ArrowRight, Inbox, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { privacyLabels } from "@/lib/api";
import type { ReactNode } from "react";

export function PrivacyBadge({ status }: { status: string }) {
  return <span className={`badge ${status === "review_required" ? "badge-amber" : status === "masked" ? "badge-green" : "badge-neutral"}`}>{status === "review_required" ? <AlertCircle size={12} /> : <ShieldCheck size={12} />}{privacyLabels[status] || status}</span>;
}
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-box" role="alert"><AlertCircle size={19} /><div><strong>Не удалось выполнить действие</strong><p>{message}</p>{retry && <button className="text-button" onClick={retry}>Повторить попытку <ArrowRight size={14} /></button>}</div></div>;
}
export function Loading({ label = "Загружаем данные…" }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={23} />{label}</div>;
}
export function Empty({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty"><div className="empty-icon"><Inbox size={27} /></div><h3>{title}</h3><p>{description}</p>{action}</div>;
}
export function PageTitle({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>{children && <div className="heading-actions">{children}</div>}</div>;
}
export function ImportLink({ children = "Импортировать обращения" }: { children?: ReactNode }) {
  return <Link className="button button-primary" href="/import">{children}<ArrowRight size={16} /></Link>;
}
