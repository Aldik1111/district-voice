import { SummaryWorkflow } from "@/components/summary-workflow";
import LegacyReports from "@/components/legacy-reports";

export default function ReportsPage() {
  return <><SummaryWorkflow /><details className="legacy-reports panel detail-section"><summary>Рабочие снимки анализа · JSON</summary><LegacyReports /></details></>;
}
