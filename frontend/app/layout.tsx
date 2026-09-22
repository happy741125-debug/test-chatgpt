import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "貨達營運中台 V3.9｜營運情報中樞",
  description: "整合營運總表、公司健康指標、LINE 與 Gmail 營運情報及每週營運檢討。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
