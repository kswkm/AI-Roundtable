import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roundtable",
  description: "여러 AI가 토론해 하나의 통합 의견을 만드는 개인용 도구",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Roundtable
          </Link>
          <nav className="nav">
            <Link href="/">질문</Link>
            <Link href="/history">기록</Link>
            <Link href="/settings">설정</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
