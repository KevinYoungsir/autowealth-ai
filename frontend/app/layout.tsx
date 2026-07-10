import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { ResearchDataProvider } from "@/components/research-data-provider";

export const metadata: Metadata = {
  title: "AutoWealth Research Dashboard",
  description: "Research-only A-share portfolio dashboard prototype"
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
