import type { Metadata } from "next";

import {
  searchMunicipalControlDocuments,
} from "../../../lib/municipal-control-documents";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Base legal municipal | Finanças",
  description:
    "Leis e normas municipais de controle e prestação de contas, com texto literal, fonte oficial e hashes verificáveis.",
};

type PageProps = Readonly<{
  searchParams: Promise<{ q?: string; pagina?: string }>;
}>;

const PAGE_SIZE = 20;

function pageNumber(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 500 ? parsed : 1;
}

function href(query: string, page: number): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (page > 1) params.set("pagina", String(page));
  const suffix = params.toString();
  return suffix ? `/financas/base-legal?${suffix}` : "/financas/base-legal";
}

export default async function MunicipalControlIndexPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = (params.q ?? "").trim().slice(0, 100);
  const page = pageNumber(params.pagina);
  const result = await searchMunicipalControlDocuments({
    query,
    pageSize: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const totalPages = result.state === "available"
    ? Math.max(1, Math.ceil(result.totalCount / PAGE_SIZE))
    : 1;

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/financas" aria-label="Voltar para Finanças">
            <span>← Finanças</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário Oficial</a>
            <a href="/sobre">Como verificamos</a>
          </nav>
        </div>
      </header>

      <section className="section legal-library" aria-labelledby="legal-library-title">
        <div className="section-heading">
          <span className="eyebrow">Fonte oficial, sem reescrita</span>
          <h1 id="legal-library-title">Base legal de controle municipal</h1>
          <p>
            Consulte o texto literal preservado de leis e normas que organizam o
            controle e a prestação de contas. Estes documentos não são demonstrativos financeiros
            e não informam, por si só, receitas, despesas ou saldo.
          </p>
        </div>

        <form className="legal-search" action="/financas/base-legal" method="get">
          <label htmlFor="legal-query">Buscar na base legal</label>
          <div>
            <input
              id="legal-query"
              name="q"
              type="search"
              defaultValue={query}
              maxLength={100}
              placeholder="Ex.: controle interno, prestação de contas"
            />
            <button type="submit">Buscar</button>
          </div>
          <p>Pesquise no título, na data ou no conteúdo integral.</p>
        </form>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Base legal temporariamente indisponível</strong>
              <p>A falha é de consulta; ela não significa ausência de documentos.</p>
            </div>
          </div>
        ) : result.documents.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhum texto corresponde à busca</strong>
              <p>Altere os termos ou <a href="/financas/base-legal">limpe a busca</a>.</p>
            </div>
          </div>
        ) : (
          <>
            <p className="legal-result-count" aria-live="polite">
              {result.totalCount.toLocaleString("pt-BR")} documento
              {result.totalCount === 1 ? "" : "s"} com texto integral verificado
            </p>
            <div className="legal-result-list">
              {result.documents.map((document) => (
                <article className="legal-result-card" key={document.documentId}>
                  <div>
                    <span>Base legal municipal</span>
                    <span>{document.referenceDate ?? "data não informada na fonte"}</span>
                  </div>
                  <h2>
                    <a href={`/financas/base-legal/${document.documentId}`}>
                      {document.title}
                    </a>
                  </h2>
                  <p className="legal-result-excerpt">{document.excerpt}</p>
                  <p className="act-evidence">
                    <a href={`/financas/base-legal/${document.documentId}`}>
                      Ler texto integral preservado →
                    </a>{" "}
                    · <a href={document.documentSourceUrl} target="_blank" rel="noreferrer">
                      fonte oficial
                    </a>{" "}
                    · hash {document.documentArtifactSha256.slice(0, 12)}…
                  </p>
                </article>
              ))}
            </div>
            {totalPages > 1 ? (
              <nav className="legislative-pagination" aria-label="Paginação da base legal">
                {page > 1 ? <a href={href(query, page - 1)}>← Anterior</a> : <span />}
                <span>Página {page} de {totalPages}</span>
                {page < totalPages ? <a href={href(query, page + 1)}>Próxima →</a> : <span />}
              </nav>
            ) : null}
          </>
        )}

        <p className="hero-note">
          O portal publica somente textos cujo arquivo oficial foi preservado e
          processado com sucesso. Documentos apenas catalogados continuam indicados
          na página de Finanças, sem inventar conteúdo ausente.
        </p>
      </section>
    </main>
  );
}
