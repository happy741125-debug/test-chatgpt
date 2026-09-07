import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "貨達營運中台 V3｜CEO 駕駛艙",
  description: "整合公司健康指標、LINE 與 Gmail 營運情報，以及 90 天回歸管理。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
