import type { Metadata } from "next";

import {
  getQueridoDiarioCollectionStatus,
  type CollectionStatusResult,
} from "../../lib/collection-status";
import {
  enrichIntegralGazetteEditions,
  getIntegralGazetteEditions,
} from "../../lib/integral-gazette-documents";
import { getIntegralGazetteListState, toIntegralGazetteIndex } from "../../lib/integral-gazette-index.mjs";
import {
  getOfficialDiaryCatalog,
  type OfficialDiaryCatalogEntry,
} from "../../lib/official-diary-catalog";
import {
  getPublicDiaryCoverage,
  type PublicDiaryCoverageResult,
} from "../../lib/public-diary-coverage";
import { IntegralGazetteIndex } from "./integral-gazette-index";
import { DiaryExtractionNotice } from "./diary-extraction-notice";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Diário Oficial organizado",
  description:
    "Texto extraído do Diário Oficial de Barreiras, organizado por edição e documento, com fontes e limitações informadas.",
  openGraph: {
    title: "Diário Oficial de Barreiras, organizado e pesquisável",
    description:
      "Consulte o texto disponível de cada edição, com fontes e limitações da extração.",
  },
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function CatalogPendingNotice({
  entries,
}: Readonly<{ entries: readonly OfficialDiaryCatalogEntry[] }>) {
  if (entries.length === 0) return null;
  return (
    <div className="collection-unavailable" role="status">
      <div>
        <strong>
          {entries.length} {entries.length === 1 ? "edição" : "edições"} no catálogo,
          sem texto disponível nesta consulta
        </strong>
        <p>
          O catálogo oficial já registrou estas edições. Elas aparecerão aqui
          após a preservação, conferência e publicação do texto extraído, sem
          alterar o texto da fonte. O catálogo, sozinho, não comprova essas etapas.
        </p>
      </div>
    </div>
  );
}

function DiaryCoverageSummary({
  collectionStatus,
  catalogCount,
  pageCount,
}: Readonly<{
  collectionStatus: CollectionStatusResult;
  catalogCount: number | null;
  pageCount: number | null;
}>) {
  return (
    <dl className="diary-coverage-summary" aria-label="Resumo da cobertura do Diário">
      <div>
        <dt>Edições preservadas</dt>
        <dd>
          {collectionStatus.state === "available"
            ? collectionStatus.data.preservedEditionCount.toLocaleString("pt-BR")
            : "—"}
        </dd>
      </div>
      <div>
        <dt>Catálogo oficial consultado</dt>
        <dd>{catalogCount === null ? "Não apurado" : catalogCount.toLocaleString("pt-BR")}</dd>
      </div>
      <div>
        <dt>Nesta página</dt>
        <dd>{pageCount === null ? "Não apurado" : pageCount.toLocaleString("pt-BR")}</dd>
      </div>
    </dl>
  );
}

function DiaryCoverageDetails({
  result,
}: Readonly<{ result: PublicDiaryCoverageResult }>) {
  if (result.state !== "available" || result.items.length === 0) return null;
  const labels = {
    complete: "janela coletada com edição preservada",
    empty: "janela coletada sem edição retornada",
    unclassified: "sem janela de coleta classificável",
  } as const;
  return (
    <details className="diary-coverage-detail">
      <summary>Ver classificação diária recente</summary>
      <p>
        A classificação abaixo usa somente janelas registradas pelo coletor.
        “Sem classificação” não significa que o Diário não exista.
      </p>
      <ul>
        {result.items.map((item) => (
          <li key={item.coverageDay}>
            <strong>
              {dateFormatter.format(new Date(`${item.coverageDay}T12:00:00-03:00`))}
            </strong>{" "}
            · {labels[item.status]} · {item.preservedEditions.toLocaleString("pt-BR")}{" "}
            {item.preservedEditions === 1 ? "edição" : "edições"}
          </li>
        ))}
      </ul>
    </details>
  );
}

type DiaryPageProps = Readonly<{
  searchParams: Promise<{ pagina?: string; q?: string }>;
}>;

const emptyNotices = {
  unavailable: {
    title: "Consulta do Diário temporariamente indisponível",
    detail: "Não foi possível consultar as edições agora. Isso não significa ausência de publicações. Tente novamente em alguns minutos.",
  },
  search_empty: {
    title: "Nenhuma edição encontrada para esta busca",
    detail: "Tente outro nome, número ou palavra. Nenhum resultado no acervo pesquisado não prova que o ato não exista na fonte oficial.",
  },
  page_empty: {
    title: "Nenhuma edição nesta página",
    detail: "Esta página não retornou registros. Volte à primeira página para consultar o acervo disponível.",
  },
  empty: {
    title: "Nenhuma edição disponível neste recorte",
    detail: "A consulta foi concluída sem edições publicadas neste recorte. Isso não comprova ausência de Diário Oficial nem cobertura histórica completa.",
  },
} as const;

function pageNumberFromSearchParams(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 500) : 1;
}

export default async function IntegralDiaryPage({
  searchParams,
}: DiaryPageProps) {
  const params = await searchParams;
  const pageNumber = pageNumberFromSearchParams(params.pagina);
  const pageSize = 20;
  const query = typeof params.q === "string" ? params.q.trim().slice(0, 120) : "";
  const querySuffix = query ? `&q=${encodeURIComponent(query)}` : "";
  const [integralResult, catalogResult, collectionStatus, coverageResult] = await Promise.all([
    getIntegralGazetteEditions({
      pageSize,
      offset: (pageNumber - 1) * pageSize,
      query,
    }),
    getOfficialDiaryCatalog(),
    getQueridoDiarioCollectionStatus(),
    getPublicDiaryCoverage(),
  ]);
  const catalogEntries =
    catalogResult.state === "available" ? catalogResult.entries : [];
  const editions =
    integralResult.state === "available"
      ? enrichIntegralGazetteEditions(integralResult.editions, catalogEntries)
      : [];
  const editionIndex = toIntegralGazetteIndex(editions);
  const catalogCount = catalogResult.state === "available" ? catalogEntries.length : null;
  const listState = getIntegralGazetteListState({
    state: integralResult.state, editionCount: editions.length,
    catalogCount, query, pageNumber,
  });
  const emptyNotice = listState === "available" || listState === "catalog_only"
    ? null : emptyNotices[listState];
  const latestCatalogCollectedAt = catalogEntries
    .map((entry) => entry.collectedAt)
    .sort()
    .at(-1);

  return (
    <main>

      <section className="section" aria-labelledby="integral-diary-title">
        <div className="section-heading">
          <span className="eyebrow">Fonte oficial, texto extraído</span>
          <h1 id="integral-diary-title">Diário Oficial organizado</h1>
          <p>
            Consulte o texto extraído dos arquivos preservados, organizado por
            edição e documento. Não substituímos os atos por resumos. A extração
            pode ter falhas; consulte as limitações abaixo antes de usar os dados.
          </p>
          {latestCatalogCollectedAt ? (
            <p className="source-freshness" role="status">
              <span className="status-dot" aria-hidden="true" />
              Catálogo oficial preservado em{" "}
              {dateTimeFormatter.format(new Date(latestCatalogCollectedAt))}
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
                . O acervo preserva{" "}
                {collectionStatus.data.preservedEditionCount} edições
                distintas. A coleta direta do catálogo oficial roda em
                paralelo.
                <br />Faixa de publicações preservadas pela API: {dateFormatter.format(
                  new Date(`${collectionStatus.data.coverageStart}T12:00:00-03:00`),
                )} a {dateFormatter.format(
                  new Date(`${collectionStatus.data.coverageEnd}T12:00:00-03:00`),
                )}. Essa é uma faixa mínima e máxima de registros, não uma
                garantia de que todos os dias tenham edição.
              </p>
            </details>
          ) : null}
        </div>

        <form className="diary-global-search" method="get">
          <label htmlFor="diary-global-query">Buscar no texto disponível do acervo</label>
          <div>
            <input
              id="diary-global-query"
              name="q"
              type="search"
              defaultValue={query}
              placeholder="nome, número, órgão ou palavra"
            />
            <button type="submit">Buscar</button>
          </div>
          {pageNumber > 1 ? <input type="hidden" name="pagina" value="1" /> : null}
        </form>

        <DiaryExtractionNotice />
        <DiaryCoverageSummary
          collectionStatus={collectionStatus}
          catalogCount={catalogCount}
          pageCount={integralResult.state === "available" ? editions.length : null}
        />
        {catalogCount === null ? (
          <p role="status">O catálogo oficial não pôde ser consultado agora. Sua contagem não foi apurada; não é zero.</p>
        ) : null}
        <DiaryCoverageDetails result={coverageResult} />

        {listState === "catalog_only" ? (
          <CatalogPendingNotice entries={catalogEntries} />
        ) : emptyNotice ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>{emptyNotice.title}</strong>
              <p>{emptyNotice.detail}</p>
              {listState === "search_empty" || listState === "page_empty" ? (
                <a href="/diario">Ver primeiras edições sem filtro</a>
              ) : null}
            </div>
          </div>
        ) : (
          <>
            <IntegralGazetteIndex editions={editionIndex} />
            {integralResult.state === "available" ? (
              <nav
                className="diary-pagination"
                aria-label="Paginação do Diário Oficial"
              >
                {pageNumber > 1 ? (
                  <a href={`/diario?pagina=${pageNumber - 1}${querySuffix}`}>
                    ← Edições mais recentes
                  </a>
                ) : (
                  <span aria-hidden="true" />
                )}
                <span>
                  Página {pageNumber} · {integralResult.offset + 1}–
                  {integralResult.offset + editions.length}
                </span>
                {integralResult.hasMore ? (
                  <a href={`/diario?pagina=${pageNumber + 1}${querySuffix}`}>
                    Edições anteriores →
                  </a>
                ) : (
                  <span aria-hidden="true" />
                )}
              </nav>
            ) : null}
          </>
        )}

        <p className="hero-note">
          Cada documento mantém o texto extraído, a edição, as páginas, a
          origem e o hash SHA-256 do artefato preservado. Encontrou um erro?{" "}
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

    </main>
  );
}
