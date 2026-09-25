import SiteNav from "./site-nav";

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="nav-shell">
        <a className="brand" href="/" aria-label="Barreiras 360, página inicial">
          <BrandMark />
          <span>Barreiras 360</span>
        </a>
        <SiteNav />
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer>
      <div className="footer-inner">
        <div>
          <a className="brand brand-footer" href="/">
            <BrandMark />
            <span>Barreiras 360</span>
          </a>
          <p>
            Informação pública de Barreiras com a fonte oficial ao lado de cada
            número. Encontrou um erro? <a href="/sobre#contestar">Conteste</a>.
          </p>
        </div>
        <nav className="footer-links" aria-label="Sobre o projeto">
          <a href="/sobre">Como funciona</a>
          <a href="/estado">Estado das fontes</a>
          <a href="/financas/cobertura">Cobertura dos dados</a>
        </nav>
      </div>
    </footer>
  );
}
