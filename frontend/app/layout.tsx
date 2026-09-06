import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "今日營運雷達｜貨達營運情報中樞",
  description: "從 LINE 工作群組整理貨達每日風險、任務、承諾與待決策事項。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
