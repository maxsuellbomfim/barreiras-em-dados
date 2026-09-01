import type { IntegralGazetteIndexEdition } from "../../lib/integral-gazette-index.mjs";

const DATE_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "Data da edição não informada";
  return DATE_FORMATTER.format(new Date(`${value}T12:00:00-03:00`));
}

function formatHash(value: string): string {
  return `${value.slice(0, 16)}…`;
}

export function IntegralGazetteIndex({
  editions,
}: Readonly<{ editions: readonly IntegralGazetteIndexEdition[] }>) {
  return (
    <div className="integral-gazette-explorer">
      <div className="integral-edition-list">
        {editions.map((edition) => (
          <article
            className="integral-edition-card"
            key={`${edition.editionYear}-${edition.edition}`}
          >
            <div className="integral-edition-head">
              <div>
                <span className="eyebrow">Edição oficial</span>
                <h2>
                  <a
                    className="integral-edition-permalink"
                    href={`/diario/${edition.editionYear}/${edition.edition}`}
                  >
                    Diário Oficial — edição {edition.edition}/{edition.editionYear}
                  </a>
                </h2>
                <p>{formatDate(edition.editionDate ?? edition.catalogDate)}</p>
              </div>
              <span className="integral-edition-count">
                {edition.documents.length} documento
                {edition.documents.length === 1 ? "" : "s"}
              </span>
            </div>

            <div className="integral-document-list">
              {edition.documents.map((document) => (
                <article
                  className="integral-document integral-document-index"
                  key={document.documentId}
                >
                  <div className="integral-document-summary">
                    <strong>{document.literalTitle}</strong>
                    <span>
                      {document.documentType ?? "Documento"} · páginas{" "}
                      {document.pageStart}–{document.pageEnd}
                    </span>
                  </div>
                  <a href={document.permalink}>Ler documento na íntegra</a>
                </article>
              ))}
            </div>

            <p className="integral-edition-evidence">
              {edition.officialPublicationUrl ? (
                <a
                  href={edition.officialPublicationUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Abrir publicação oficial
                </a>
              ) : edition.catalogUrl ? (
                <a href={edition.catalogUrl} target="_blank" rel="noreferrer">
                  Abrir catálogo oficial
                </a>
              ) : (
                <span>Fonte oficial preservada no acervo</span>
              )}{" "}
              · hash {formatHash(edition.artifactSha256)}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
