"use client";

import { usePathname } from "next/navigation";

// Ordem pelo que o cidadão procura primeiro: dinheiro, compras e quem decide.
// Os mesmos nomes valem em todo o site.
export const SITE_SECTIONS = [
  { href: "/financas", label: "Dinheiro público" },
  { href: "/licitacoes", label: "Compras" },
  { href: "/representantes", label: "Quem decide" },
  { href: "/diario", label: "Diário Oficial" },
  { href: "/atos", label: "Nomeações" },
  { href: "/camara", label: "Câmara" },
  { href: "/recursos", label: "Emendas" },
] as const;

function isCurrent(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Links({ pathname }: Readonly<{ pathname: string }>) {
  return SITE_SECTIONS.map((section) => (
    <a
      key={section.href}
      href={section.href}
      aria-current={isCurrent(pathname, section.href) ? "page" : undefined}
    >
      {section.label}
    </a>
  ));
}

export default function SiteNav() {
  const pathname = usePathname() ?? "/";
  return (
    <>
      <nav className="nav-links" aria-label="Seções do site">
        <Links pathname={pathname} />
      </nav>
      {/* Sem JavaScript: o menu do celular abre e fecha com <details>. */}
      <details className="nav-menu">
        <summary>Menu</summary>
        <nav className="nav-menu-panel" aria-label="Seções do site">
          <Links pathname={pathname} />
          <a href="/sobre">Como funciona</a>
        </nav>
      </details>
    </>
  );
}
