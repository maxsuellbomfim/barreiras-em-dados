import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Barreiras em Dados",
    template: "%s | Barreiras em Dados",
  },
  description:
    "Informação pública de Barreiras com fonte, contexto e linguagem clara.",
  applicationName: "Barreiras em Dados",
  category: "civic tech",
  keywords: [
    "Barreiras",
    "Bahia",
    "transparência pública",
    "dados abertos",
    "controle social",
  ],
  openGraph: {
    type: "website",
    locale: "pt_BR",
    title: "Barreiras em Dados",
    description:
      "Informação pública de Barreiras com fonte, contexto e linguagem clara.",
    siteName: "Barreiras em Dados",
  },
  twitter: {
    card: "summary",
    title: "Barreiras em Dados",
    description:
      "Informação pública de Barreiras com fonte, contexto e linguagem clara.",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f5f7fb",
  colorScheme: "light",
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
