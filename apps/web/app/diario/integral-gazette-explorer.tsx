"use client";

import { useMemo, useState } from "react";

import type { IntegralGazetteEdition } from "../../lib/integral-gazette-documents";

const DATE_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "Data da edição não informada";
  return DATE_FORMATTER.format(new Date(value + "T12:00:00-03:00"));
}

function formatHash(value: string): string {
  return value.slice(0, 16) + "…";
}

function visibleEdition(
  edition: IntegralGazetteEdition,
  query: string,
): IntegralGazetteEdition | null {
  const normalized = query.trim().toLocaleLowerCase("pt-BR");
  if (!normalized) return edition;
  const documents = edition.documents.filter((document) =>
    (document.literalTitle + "\n" + document.fullText)
      .toLocaleLowerCase("pt-BR")
      .includes(normalized),
  );
  return documents.length === 0 ? null : { ...edition, documents };
}

function DocumentDetails({
  document,
}: Readonly<{
  document: IntegralGazetteEdition["documents"][number];
}>) {
  const fallback = document.publicationStatus === "edition_fallback";
  return (
    <details
      className="integral-document"
      id={`document-${document.documentId}`}
    >
      <summary>
        <span className="integral-document-summary">
          <strong>{document.literalTitle}</strong>
          <span>
            {document.documentType ?? "Documento"} · páginas {document.pageStart}–
            {document.pageEnd}
          </span>
        </span>
        <span className="integral-document-chevron" aria-hidden="true">
          +
        </span>
      </summary>
      <div className="integral-document-body">
        {fallback ? (
          <p className="integral-fallback-note">
            Edição integral — separação segura indisponível
          </p>
        ) : null}
        <pre className="integral-document-text">{document.fullText}</pre>
        <p className="integral-document-evidence">
          Texto literal preservado · hash {formatHash(document.textSha256)}
        </p>
      </div>
    </details>
  );
}

export function IntegralGazetteExplorer({
  editions,
  initialQuery = "",
}: Readonly<{
  editions: readonly IntegralGazetteEdition[];
  initialQuery?: string;
}>) {
  const [query, setQuery] = useState(initialQuery);
  const visibleEditions = useMemo(
    () =>
      editions
        .map((edition) => visibleEdition(edition, query))
        .filter((edition): edition is IntegralGazetteEdition => edition !== null),
    [editions, query],
  );

  return (
    <div className="integral-gazette-explorer">
      <label className="integral-search-label" htmlFor="integral-search">
        Buscar no texto integral
      </label>
      <input
        id="integral-search"
        className="integral-search"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="número, nome, órgão ou palavra"
      />
      {visibleEditions.length === 0 ? (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Nenhuma edição encontrada</strong>
            <p>Experimente outra palavra ou limpe a busca.</p>
          </div>
        </div>
      ) : (
        <div className="integral-edition-list">
          {visibleEditions.map((edition) => (
            <article
              className="integral-edition-card"
              key={edition.editionYear + "-" + edition.edition}
            >
              <div className="integral-edition-head">
                <div>
                  <span className="eyebrow">Edição oficial</span>
                  <h2>
                    <a
                      className="integral-edition-permalink"
                      href={`/diario/${edition.editionYear}/${edition.edition}`}
                    >
                      Diário Oficial — edição {edition.edition}/
                      {edition.editionYear}
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
                  <DocumentDetails
                    document={document}
                    key={document.documentId}
                  />
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
      )}
    </div>
  );
}
