import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://barreiras-em-dados.vercel.app"),
  title: {
    default: "Barreiras 360",
    template: "%s | Barreiras 360",
  },
  description:
    "O panorama público de Barreiras: contas, decisões, obras e representantes com fonte e contexto.",
  applicationName: "Barreiras 360",
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
    title: "Barreiras 360",
    description:
      "O panorama público de Barreiras: contas, decisões, obras e representantes com fonte e contexto.",
    siteName: "Barreiras 360",
  },
  twitter: {
    card: "summary_large_image",
    title: "Barreiras 360",
    description:
      "O panorama público de Barreiras: contas, decisões, obras e representantes com fonte e contexto.",
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
