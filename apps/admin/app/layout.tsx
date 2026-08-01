import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Revisão | Barreiras em Dados",
  description:
    "Área interna de revisão humana. Nada aqui é público até ser aprovado.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <header className="topbar">
          <span className="topbar-brand">
            <span className="topbar-dot" aria-hidden="true" />
            Barreiras em Dados · Revisão
          </span>
          <a
            className="topbar-link"
            href="https://barreiras-em-dados.vercel.app/atos"
            target="_blank"
            rel="noreferrer"
          >
            Ver site público ↗
          </a>
        </header>
        {children}
        <footer className="page-foot">
          Área interna de revisão humana — cada decisão fica registrada com
          autoria, justificativa e data.
        </footer>
      </body>
    </html>
  );
}
