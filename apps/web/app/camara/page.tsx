import type { Metadata } from "next";

import { getCamaraLegislativeAuthorSummary, getCamaraLegislativePage, type CamaraLegislativeFilters } from "../../lib/camara-legislative";
import { CamaraLawsExplorer } from "./laws-explorer";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Leis e indicações da Câmara Municipal",
  description:
    "Leis e registros legislativos de Barreiras preservados a partir da API oficial da Câmara Municipal.",
};

function pageNumber(value: unknown): number {
  const parsed = typeof value === "string" ? Number(value) : 1;
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 1000 ? parsed : 1;
}

function boundedText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim().slice(0, 200);
  return text || null;
}

function legislativeFilters(params: Readonly<Record<string, string | undefined>>): CamaraLegislativeFilters {
  const kind = params.kind === "lei" || params.kind === "indicacao" ? params.kind : null;
  const parsedYear = typeof params.year === "string" ? Number(params.year) : NaN;
  const year = Number.isSafeInteger(parsedYear) && parsedYear >= 1900 && parsedYear <= 2200 ? parsedYear : null;
  return { query: boundedText(params.q), author: boundedText(params.author), kind, year };
}

export default async function CamaraPage({
  searchParams,
}: Readonly<{ searchParams: Promise<{ page?: string; q?: string; kind?: string; year?: string; author?: string }> }>) {
  const params = await searchParams;
  const page = pageNumber(params.page);
  const filters = legislativeFilters(params);
  const [result, authorSummary] = await Promise.all([
    getCamaraLegislativePage(page, 50, filters),
    getCamaraLegislativeAuthorSummary(filters),
  ]);
  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">← Barreiras 360</a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/representantes">Representantes</a>
            <a href="/licitacoes">Licitações</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>
      <section className="section" aria-labelledby="camara-title">
        <div className="section-heading">
          <span className="eyebrow">Câmara Municipal de Barreiras</span>
          <h1 id="camara-title">Leis e indicações em linguagem acessível</h1>
          <p>
            Registros da API oficial da Câmara, com título, ementa, autoria quando
            publicada, identificador, data e documento. A autoria aparece somente
            quando a fonte a informa; nenhuma associação é feita por semelhança de nome.
          </p>
          <p className="hero-note">
            A maior parte das leis pode não trazer autoria individual na fonte.
            Quando há autoria, reproduzimos o texto como publicado. Caixa alta,
            nome de urna, coautorias e grafias diferentes podem representar
            registros distintos; por isso não consolidamos pessoas
            automaticamente.
          </p>
        </div>
        {!result ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Atividade legislativa temporariamente indisponível</strong>
              <p>Isso indica falha de consulta ou ausência de projeção publicada, não ausência de leis ou indicações.</p>
            </div>
          </div>
        ) : result.items.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>A coleta legislativa ainda não começou</strong>
              <p>A fonte foi configurada; leis e indicações aparecerão após uma coleta válida.</p>
            </div>
          </div>
        ) : (
          <CamaraLawsExplorer
            items={result.items}
            totalCount={result.totalCount}
            page={result.page}
            pageSize={result.pageSize}
            initialFilters={filters}
            authorSummary={authorSummary}
          />
        )}
        <p className="hero-note">
          Fonte: <a href="https://portaldatransparencia.cmbarreiras.ba.gov.br/dados-abertos/" target="_blank" rel="noreferrer">Portal de dados abertos da Câmara</a>. Encontrou erro? <a href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/camara&labels=correcao" target="_blank" rel="noreferrer">Abra uma correção pública</a>.
        </p>
      </section>
      <footer><div className="footer-inner"><div><a className="brand brand-footer" href="/">Barreiras 360</a><p>Informação pública de Barreiras para acompanhar a cidade com clareza.</p></div><div className="footer-status"><span className="status-dot" />Atividade legislativa oficial, sem autoria inferida</div></div></footer>
    </main>
  );
}
