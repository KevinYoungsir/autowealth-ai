import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { ResearchDataProvider } from "@/components/research-data-provider";
import { ui } from "@/i18n";

export const metadata: Metadata = {
  title: ui.metadata.title,
  description: ui.metadata.description
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <ResearchDataProvider>
          <AppShell>{children}</AppShell>
        </ResearchDataProvider>
      </body>
    </html>
  );
}
