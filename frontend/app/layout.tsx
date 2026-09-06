import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "貨達營運情報中樞",
  description: "LINE-first Work Intelligence Hub",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
