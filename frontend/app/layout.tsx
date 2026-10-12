import type { Metadata } from "next";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Голос района — рабочее пространство", template: "%s · Голос района" },
  description: "Локальная платформа анализа и проверки обращений граждан Казахстана.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body><Shell>{children}</Shell></body></html>;
}
