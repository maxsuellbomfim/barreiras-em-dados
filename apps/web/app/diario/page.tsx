import type { Metadata } from "next";

import {
  getEditionDigests,
  type DigestItem,
  type EditionDigest,
} from "../../lib/edition-digests";
import {
  getOfficialDiaryCatalog,
  type OfficialDiaryCatalogEntry,
} from "../../lib/official-diary-catalog";
import { getQueridoDiarioCollectionStatus } from "../../lib/collection-status";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Diário Oficial traduzido",
  description:
    "Cada edição do Diário Oficial de Barreiras resumida em linguagem " +
    "simples, com citação literal do texto oficial em cada item.",
};

const TYPE_LABELS: Readonly<Record<string, string>> = {
  nomeacao: "Nomeação",
  exoneracao: "Exoneração",
  contrato: "Contrato",
  licitacao: "Licitação",
  decreto: "Decreto",
  portaria: "Portaria",
  aviso: "Aviso",
  outro: "Outros",
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

function ItemRow({ item }: Readonly<{ item: DigestItem }>) {
  return (
    <li className="digest-item">
      <span className="digest-item-type">
        {TYPE_LABELS[item.tipo] ?? "Outros"}
      </span>
      <div>
        <h3>{item.titulo}</h3>
        <details className="digest-item-explanation">
          <summary>Explicação em palavras simples</summary>
          <p>{item.resumo}</p>
        </details>
        <details>
          <summary>Citação do texto oficial</summary>
          <pre className="act-excerpt">“{item.trecho}”</pre>
        </details>
      </div>
    </li>
  );
}

function DigestCard({ digest }: Readonly<{ digest: EditionDigest }>) {
  const officialDate = digest.officialDate ?? digest.editionDate;
  return (
    <article className="digest-card" aria-label="Resumo de edição">
      <div className="track-top">
        <span>
          Edição {digest.edition.toLocaleString("pt-BR")}/
          {digest.editionYear}
        </span>
        <span className="track-status">
          {officialDate
            ? `Publicada em ${new Intl.DateTimeFormat("pt-BR", {
                day: "2-digit",
                month: "short",
                year: "numeric",
                timeZone: "America/Bahia",
              }).format(new Date(`${officialDate}T12:00:00-03:00`))}`
            : "Data da edição não informada"}
        </span>
      </div>
      {digest.officialTitle ? (
        <h2 className="digest-card-title">{digest.officialTitle}</h2>
      ) : null}
      {digest.officialSummary ? (
        <details className="digest-official-source">
          <summary>Resumo oficial da Prefeitura</summary>
          <p>{digest.officialSummary}</p>
          <small>
            Texto transcrito do catálogo oficial, sem interpretação.
            {digest.officialPublicationUrl ? (
              <a
                href={digest.officialPublicationUrl}
                target="_blank"
                rel="noreferrer"
              >
                Abrir publicação oficial
              </a>
            ) : null}
          </small>
        </details>
      ) : null}
      <p className="digest-card-meta">
        {digest.items.length} {digest.items.length === 1 ? "item" : "itens"}
        {digest.partial ? " · resumo parcial" : ""}
      </p>
      <ul className="digest-items">
        {digest.items.map((item, index) => (
          <ItemRow key={`${digest.digestId}-${index}`} item={item} />
        ))}
      </ul>
      <p className="act-evidence">
        {digest.gazetteUrl ? (
          <a href={digest.gazetteUrl} target="_blank" rel="noreferrer">
            Ver a edição oficial (PDF)
          </a>
        ) : (
          <span>Edição preservada no acervo verificável</span>
        )}{" "}
        · hash {digest.artifactSha256.slice(0, 12)}… · publicado em{" "}
        {dateTimeFormatter.format(new Date(digest.publishedAt))}
      </p>
      <p className="act-review-mode">
        Resumo gerado com IA e verificado por código: cada item traz uma
        citação literal conferida no texto oficial; itens sem citação são
        descartados. Sujeito a correção — e toda correção fica registrada.
      </p>
    </article>
  );
}

function CatalogCard({
  entry,
}: Readonly<{ entry: OfficialDiaryCatalogEntry }>) {
  return (
    <article className="digest-card" aria-label="Edição oficial do Diário">
      <div className="track-top">
        <span>
          Edição {entry.edition.toLocaleString("pt-BR")}/{entry.editionYear}
        </span>
        <span className="track-status">
          Publicada em{" "}
          {new Intl.DateTimeFormat("pt-BR", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            timeZone: "America/Bahia",
          }).format(new Date(entry.editionDate + "T12:00:00-03:00"))}
        </span>
      </div>
      <h2 className="digest-card-title">
        {entry.officialTitle ?? "Diário Oficial de Barreiras"}
      </h2>
      <p className="digest-card-meta">
        Registro oficial do catálogo da Prefeitura
      </p>
      {entry.officialSummary ? (
        <details className="digest-official-source">
          <summary>Resumo oficial da Prefeitura</summary>
          <p>{entry.officialSummary}</p>
        </details>
      ) : null}
      <details className="digest-official-source">
        <summary>Explicação detalhada ainda não disponível</summary>
        <p>
          Esta edição já foi encontrada no catálogo oficial e sua data está
          confirmada. O texto integral ainda não foi preservado ou processado;
          por isso não inventamos uma tradução por IA. Assim que o documento
          estiver disponível, os itens explicados e suas citações aparecerão
          aqui automaticamente.
        </p>
      </details>
      <p className="act-evidence">
        {entry.officialPublicationUrl ? (
          <a
            href={entry.officialPublicationUrl}
            target="_blank"
            rel="noreferrer"
          >
            Abrir publicação oficial
          </a>
        ) : entry.catalogUrl ? (
          <a href={entry.catalogUrl} target="_blank" rel="noreferrer">
            Abrir catálogo oficial
          </a>
        ) : null}{" "}
        · hash {entry.artifactSha256.slice(0, 12)}… · catálogo coletado em{" "}
        {dateTimeFormatter.format(new Date(entry.collectedAt))}
      </p>
      <p className="act-review-mode">
        Registro espelhado da fonte oficial, sem interpretação ou conclusão.
      </p>
    </article>
  );
}

export default async function EditionDigestsPage() {
  const [result, catalogResult, collectionStatus] = await Promise.all([
    getEditionDigests(),
    getOfficialDiaryCatalog(),
    getQueridoDiarioCollectionStatus(),
  ]);
  const digests = result.state === "available" ? result.digests : [];
  const catalogEntries =
    catalogResult.state === "available" ? catalogResult.entries : [];
  const digestEditions = new Set(digests.map((digest) => digest.edition));
  const catalogOnlyEntries = catalogEntries.filter(
    (entry) => !digestEditions.has(entry.edition),
  );
  const latestCatalogCollectedAt = catalogEntries
    .map((entry) => entry.collectedAt)
    .sort()
    .at(-1);

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/atos">Atos públicos</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="digests-title">
        <div className="section-heading">
          <span className="eyebrow">O Diário inteiro, em palavras simples</span>
          <h1 id="digests-title">Diário Oficial traduzido</h1>
          <p>
            Cada edição resumida item a item — nomeações, contratos,
            licitações, decretos e avisos — em linguagem que qualquer pessoa
            entende. Todo item carrega uma citação literal do texto oficial,
            conferida por código antes de publicar. Isto é um espelho
            traduzido do registro oficial, não uma avaliação.
          </p>
          {latestCatalogCollectedAt ? (
            <p className="source-freshness" role="status">
              <span className="status-dot" aria-hidden="true" />
              Catálogo oficial preservado em{" "}
              {dateTimeFormatter.format(new Date(latestCatalogCollectedAt))}
              {" "}· atualização automática ativa
            </p>
          ) : null}
          {collectionStatus.state === "available" ? (
            <details className="digest-official-source">
              <summary>Ver estado da coleta automática</summary>
              <p>
                A API do Querido Diário foi consultada pela última vez em{" "}
                {dateTimeFormatter.format(
                  new Date(collectionStatus.data.lastSuccessfulAt),
                )}
                . O acervo cobre de{" "}
                {new Intl.DateTimeFormat("pt-BR", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                  timeZone: "America/Bahia",
                }).format(
                  new Date(`${collectionStatus.data.coverageStart}T12:00:00-03:00`),
                )}{" "}
                a{" "}
                {new Intl.DateTimeFormat("pt-BR", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                  timeZone: "America/Bahia",
                }).format(
                  new Date(`${collectionStatus.data.coverageEnd}T12:00:00-03:00`),
                )}{" "}
                e preserva {collectionStatus.data.preservedEditionCount} edições
                distintas. A coleta direta do catálogo oficial roda em paralelo;
                uma nova publicação só aparece quando a fonte a disponibiliza.
              </p>
            </details>
          ) : null}
        </div>

        {result.state === "unavailable" && catalogResult.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Resumos temporariamente indisponíveis</strong>
              <p>
                Isso representa uma falha de consulta, não ausência de dados.
                Tente novamente em alguns minutos.
              </p>
            </div>
          </div>
        ) : digests.length === 0 && catalogOnlyEntries.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Os primeiros resumos estão a caminho</strong>
              <p>
                As edições já estão preservadas no acervo; os resumos são
                gerados e verificados automaticamente a cada coleta e
                aparecerão aqui em breve.
              </p>
            </div>
          </div>
        ) : (
          <div className="digest-grid">
            {[
              ...digests.map((digest) => ({
                kind: "digest" as const,
                edition: digest.edition,
                digest,
              })),
              ...catalogOnlyEntries.map((entry) => ({
                kind: "catalog" as const,
                edition: entry.edition,
                entry,
              })),
            ]
              .sort((left, right) => right.edition - left.edition)
              .map((card) =>
                card.kind === "digest" ? (
                  <DigestCard key={card.digest.digestId} digest={card.digest} />
                ) : (
                  <CatalogCard key={card.entry.catalogId} entry={card.entry} />
                ),
              )}
          </div>
        )}

        <p className="hero-note">
          Metodologia: resumo assistido por IA com âncora literal verificada
          por código versionado (ADR 0013); publicação automática auditada e
          reversível. Encontrou um erro?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/diario&labels=correcao"
            target="_blank"
            rel="noreferrer"
          >
            Abra um pedido público de correção
          </a>
          .
        </p>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="/">
              <span>Barreiras 360</span>
            </a>
            <p>
              Informação pública de Barreiras para acompanhar a cidade com
              clareza.
            </p>
          </div>
          <div className="footer-status">
            <span className="status-dot" />
            Resumos ancorados no documento oficial, item a item
          </div>
        </div>
      </footer>
    </main>
  );
}
