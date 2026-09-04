import type { Metadata } from "next";

import {
  getPublicCurrentParliamentaryTransfers,
  getPublicParliamentaryTransfers,
  getPublicParliamentaryTransferRankings,
  parliamentaryTransferAuthorAnchor,
  type BahiaStateLoaAmendment,
  type BahiaStateLoaAmendmentRanking,
  type FederalTransferProposal,
  type FederalTransferScopeSummary,
  type HistoricalParliamentaryAmendment,
  type HistoricalParliamentaryAmendmentRanking,
  type ParliamentaryTransfer,
  type ParliamentaryTransferCoverage,
  type ParliamentaryTransferReconciliationSummary,
  type ParliamentaryTransferRanking,
  type ParliamentaryTransferRankingsResult,
  type ReconciledParliamentaryTransferRanking,
  type StateLoaExecutionRecord,
  type StateLoaExecutionGroup,
  type StateLoaExecutionSummary,
} from "../../lib/parliamentary-transfers";
import { buildCurrentTransferCitizenSummary } from "../../lib/parliamentary-transfer-citizen-summary.mjs";
import { resolveTransferSourceSelection } from "../../lib/parliamentary-transfer-source-filter.mjs";
import { resolveCurrentFederalTransferYear } from "../../lib/parliamentary-transfer-year-filter.mjs";
import { formatBrlDecimal } from "../../lib/revenues";
import { stateLoaExecutionStatusCopy } from "../../lib/state-loa-execution-citizen-copy.mjs";
import {
  resolveStateLoaYear,
  stateLoaYears,
} from "../../lib/state-loa-year-filter.mjs";
import {
  resolveStateLoaStudyFilters,
  stateLoaStudyPageHref,
  type StateLoaStudyAuthor,
  type StateLoaStudyFilters,
} from "../../lib/state-loa-study.mjs";
import {
  getPublicCguFederalAmendments,
  getPublicCguFederalAmendmentLegislatureRankings,
  type CguFederalAmendment,
  type CguFederalAmendmentRanking,
  type CguFederalAmendmentsResult,
} from "../../lib/cgu-federal-amendments";
import {
  getPublicCguFederalAmendmentDocuments,
  type CguFederalAmendmentDocument,
  type CguFederalAmendmentDocumentFilters,
  type CguFederalAmendmentDocumentsResult,
} from "../../lib/cgu-federal-amendment-documents";
import {
  cguExecutionAuthorHref,
  cguExecutionResultCountCopy,
  filterCguExecutionAmendments,
  resolveCguExecutionFilters,
} from "../../lib/cgu-execution-filter.mjs";
import {
  buildCguAuthorCoverageSummary,
  type CguAuthorCoverageSummary,
} from "../../lib/cgu-author-coverage.mjs";
import { getPublicFederalTransferSourceCoverage } from
  "../../lib/federal-transfer-source-coverage";
import {
  groupFederalTransferSourceCoverage,
  type FederalTransferSourceCoverage,
  type FederalTransferSourceKey,
} from "../../lib/federal-transfer-source-coverage.mjs";
import { getPublicStateAmendmentSourceCoverage } from
  "../../lib/state-amendment-source-coverage";
import type { StateAmendmentSourceCoverage } from
  "../../lib/state-amendment-source-coverage.mjs";
import { getPublicBahiaSpecialTransfers } from
  "../../lib/bahia-special-transfers";
import { getPublicBahiaStateExecutionCoverage } from
  "../../lib/bahia-state-execution-coverage";
import type { BahiaStateExecutionCoverage } from
  "../../lib/bahia-state-execution-coverage.mjs";
import { getPublicParliamentaryLegislatureRankings } from
  "../../lib/legislature-transfer-rankings";
import { getPublicParliamentaryLegislatureCoverage } from
  "../../lib/legislature-transfer-coverage";
import { getPublicParliamentaryLegislatureYearCoverage } from
  "../../lib/legislature-transfer-year-coverage";
import LegislatureTransferRankings from "./legislature-transfer-rankings";
import BahiaSpecialTransfersPanel from "./bahia-special-transfers-panel";
import BahiaStateExecutionCoveragePanel from
  "./bahia-state-execution-coverage-panel";
import ShareLink from "../share-link";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Recursos destinados a Barreiras",
  description:
    "Propostas federais e emendas destinadas a Barreiras, com autoria e estágios financeiros separados por fonte oficial.",
  openGraph: {
    title: "Quem destinou recursos para Barreiras",
    description:
      "Emendas federais e estaduais, deputado por deputado, com valores oficiais e o documento que comprova cada etapa.",
  },
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});
const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "data não encontrada na fonte consultada";
  const parsed = new Date(`${value}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function authorKindLabel(kind: ParliamentaryTransfer["authorKind"]): string {
  if (kind === "person") return "Autoria individual";
  if (kind === "commission") return "Autoria de comissão";
  if (kind === "bench") return "Autoria de bancada";
  if (kind === "collective") return "Autoria coletiva";
  return "Autoria informada pela fonte";
}

function unavailableAmount(stage: "commitment" | "payment"): string {
  return stage === "commitment"
    ? "Empenho não encontrado nos endpoints consultados"
    : "Pagamento não encontrado nos endpoints consultados";
}

function coverageDescription(row: ParliamentaryTransferCoverage): string {
  if (
    row.coverageStatus === "complete" &&
    row.proposalCount !== null &&
    row.publishedAmendmentCount !== null
  ) {
    return `API atual consultada: ${row.proposalCount.toLocaleString("pt-BR")} proposta(s); ${row.publishedAmendmentCount.toLocaleString("pt-BR")} emenda(s) publicada(s).`;
  }
  if (row.coverageStatus === "empty") {
    return "API atual consultada: nenhuma proposta encontrada para o ano.";
  }
  if (row.coverageStatus === "partial") {
    return "Coleta incompleta: ainda não é possível concluir quantas propostas existem.";
  }
  if (row.coverageStatus === "failed") {
    return "Coleta com falha: a fonte não pôde ser conferida por inteiro.";
  }
  if (row.coverageStatus === "blocked") {
    return "Coleta bloqueada pela fonte: este ano precisa de nova tentativa.";
  }
  return "Ano ainda não classificado.";
}

function CurrentFederalFreshness({
  coverage,
}: Readonly<{ coverage: ParliamentaryTransferCoverage | null }>) {
  if (coverage === null) {
    return (
      <p className="transfer-current-freshness" data-status="unavailable">
        <strong>Cobertura anual indisponível.</strong> A data da última consulta
        não pôde ser carregada agora; isso não significa ausência de recursos.
      </p>
    );
  }

  const statusCopy: Readonly<Record<
    ParliamentaryTransferCoverage["coverageStatus"],
    string
  >> = {
    complete: "Cobertura anual completa.",
    empty: "Fonte consultada sem proposta atribuída a Barreiras.",
    partial: "Coleta anual ainda incompleta.",
    failed: "A última coleta anual falhou.",
    blocked: "A fonte bloqueou a coleta anual.",
    unclassified: "O ano ainda não foi classificado.",
  };

  return (
    <p
      className="transfer-current-freshness"
      data-status={coverage.coverageStatus}
    >
      <strong>{statusCopy[coverage.coverageStatus]}</strong>{" "}
      {coverage.lastAttemptedAt ? (
        <>
          Fonte oficial conferida em{" "}
          <time dateTime={coverage.lastAttemptedAt}>
            {dateTimeFormatter.format(new Date(coverage.lastAttemptedAt))}
          </time>.
        </>
      ) : (
        "A fonte não informou a data da última tentativa."
      )}
    </p>
  );
}

function CoveragePanel({
  rows,
}: Readonly<{ rows: readonly ParliamentaryTransferCoverage[] | null }>) {
  return (
    <details className="transfer-methodology transfer-coverage">
      <summary>Ver quais anos e fontes já foram conferidos</summary>
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Cobertura da API atual</span>
          <h2>Quais anos já conferimos?</h2>
        </div>
        <p>O estado é calculado por código para cada ano, de forma independente.</p>
      </div>
      {rows === null ? (
        <p className="transfer-coverage-unavailable">
          O diagnóstico anual está temporariamente indisponível. Isso não altera
          nem apaga os registros oficiais exibidos abaixo.
        </p>
      ) : (
        <ul className="transfer-coverage-grid">
          {rows.map((row) => (
            <li data-status={row.coverageStatus} key={row.fiscalYear}>
              <strong>{row.fiscalYear}</strong>
              <span>{coverageDescription(row)}</span>
              {row.lastAttemptedAt ? (
                <small>
                  Última tentativa: {dateTimeFormatter.format(new Date(row.lastAttemptedAt))}
                </small>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <p className="transfer-coverage-caveat">
        Nenhuma proposta encontrada na API atual não prova ausência em outras bases
        oficiais. Por isso, o arquivo histórico federal aparece em uma seção
        separada abaixo, sem transformar dado não coletado em zero.
      </p>
    </details>
  );
}

const FEDERAL_COVERAGE_SOURCES: readonly Readonly<{
  key: FederalTransferSourceKey;
  label: string;
}>[] = [
  { key: "cgu_execution", label: "Retrato agregado · CGU" },
  { key: "cgu_documents", label: "Documentos anuais · CGU" },
  { key: "transferegov_historical", label: "Arquivo de convênios" },
  { key: "transferegov_current", label: "API atual de convênios" },
];

function federalCoverageStatusCopy(
  row: FederalTransferSourceCoverage | undefined,
): string {
  if (!row) return "fora do recorte desta fonte";
  if (row.coverageStatus === "observed") {
    return row.recordCount === 1
      ? "1 linha oficial encontrada"
      : `${row.recordCount?.toLocaleString("pt-BR")} linhas oficiais encontradas`;
  }
  if (row.coverageStatus === "empty") {
    return "nenhuma linha atribuída a Barreiras";
  }
  if (row.coverageStatus === "partial") return "coleta parcial";
  if (row.coverageStatus === "failed") return "consulta falhou";
  if (row.coverageStatus === "blocked") return "fonte bloqueou a coleta";
  return "ainda não classificado";
}

function FederalTransferSourceCoveragePanel({
  rows,
}: Readonly<{ rows: readonly FederalTransferSourceCoverage[] | null }>) {
  const groups = rows ? groupFederalTransferSourceCoverage(rows) : [];
  const sourceUrls = new Map<FederalTransferSourceKey, string>();
  for (const row of rows ?? []) sourceUrls.set(row.sourceKey, row.sourceUrl);

  return (
    <details className="transfer-methodology transfer-source-coverage">
      <summary>Quais anos cada fonte federal já conferiu?</summary>
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Cobertura verificável</span>
          <h2>O que foi encontrado em cada base oficial</h2>
        </div>
        <p>
          Cada coluna é uma fonte diferente. Elas não são somadas e podem cobrir
          caminhos distintos do recurso público.
        </p>
      </div>
      <p>
        <strong>“Nenhuma linha atribuída a Barreiras”</strong> significa que a
        fonte foi consultada e não devolveu registro municipal naquele ano. Isso
        não prova ausência em outras bases e <strong>não significa valor financeiro zero</strong>.
      </p>
      <p>
        No arquivo histórico, registros de consórcios regionais só entram na
        contagem quando o objeto cita Barreiras ou outra evidência territorial
        confirma o município. Cadastrar o proponente em Barreiras, sozinho, não
        basta para atribuir o recurso à cidade.
      </p>
      {groups.length === 0 ? (
        <p className="transfer-coverage-unavailable">
          O diagnóstico comparativo está temporariamente indisponível. Os registros
          oficiais já publicados abaixo permanecem preservados.
        </p>
      ) : (
        <div className="transfer-source-coverage-scroll">
          <table>
            <caption>Cobertura anual das quatro séries federais consultadas</caption>
            <thead>
              <tr>
                <th scope="col">Ano</th>
                {FEDERAL_COVERAGE_SOURCES.map((source) => (
                  <th scope="col" key={source.key}>
                    {sourceUrls.has(source.key) ? (
                      <a href={sourceUrls.get(source.key)} rel="noreferrer" target="_blank">
                        {source.label}
                      </a>
                    ) : source.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <tr key={group.fiscalYear}>
                  <th scope="row">{group.fiscalYear}</th>
                  {FEDERAL_COVERAGE_SOURCES.map((source) => {
                    const row = group.sources.find((item) => item.sourceKey === source.key);
                    return (
                      <td data-status={row?.coverageStatus ?? "outside"} key={source.key}>
                        <strong>{federalCoverageStatusCopy(row)}</strong>
                        {row?.lastAttemptedAt ? (
                          <small>
                            Conferido em {dateTimeFormatter.format(new Date(row.lastAttemptedAt))}
                          </small>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function stateLoaCoverageCopy(row: StateAmendmentSourceCoverage): string {
  if (row.loaStatus === "observed") {
    return `${row.amendmentCount?.toLocaleString("pt-BR")} emenda(s) · ${formatBrlDecimal(row.authorizedAmount!)}`;
  }
  if (row.loaStatus === "empty") return "anexo conferido, sem linha para Barreiras";
  if (row.loaStatus === "blocked" && row.fiscalYear === 2021) {
    return "link rotulado como 2021 aponta para o anexo de 2020";
  }
  if (row.loaStatus === "partial") return "anexo coletado parcialmente";
  if (row.loaStatus === "failed") return "consulta ao anexo falhou";
  return "anexo ainda não classificado";
}

function stateExecutionCoverageCopy(row: StateAmendmentSourceCoverage): string {
  if (row.executionStatus === "observed") {
    return `${row.matchedCount?.toLocaleString("pt-BR")} ligação(ões) confirmada(s)`;
  }
  if (row.executionStatus === "partial") {
    return `${row.matchedCount?.toLocaleString("pt-BR")} segura(s) · ${row.ambiguousCount?.toLocaleString("pt-BR")} ambígua(s) · ${row.notFoundCount?.toLocaleString("pt-BR")} não localizada(s)`;
  }
  if (row.executionStatus === "blocked_missing_official_key") {
    return "fonte coletada, mas sem chave oficial para ligar a execução";
  }
  if (row.executionStatus === "scope_not_indexed") {
    return "execução territorial ainda não indexada";
  }
  if (row.executionStatus === "loa_unavailable") {
    return "não comparável sem anexo válido";
  }
  return "execução ainda não classificada";
}

function StateAmendmentSourceCoveragePanel({
  rows,
}: Readonly<{ rows: readonly StateAmendmentSourceCoverage[] | null }>) {
  const sourceUrl = rows?.[0]?.sourceUrl;
  return (
    <details className="transfer-methodology transfer-source-coverage">
      <summary>Quais anos estaduais já foram conferidos?</summary>
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Cobertura verificável</span>
          <h2>Anexo da LOA e execução são duas etapas diferentes</h2>
        </div>
        <p>
          Primeiro confirmamos a autorização no orçamento. Depois tentamos ligar
          essa autorização à execução financeira estadual sem ambiguidade.
          Nos anexos de 2022 a 2025, a fonte não publica os códigos necessários
          para essa ligação. Isso não significa que o recurso não foi executado:
          significa apenas que não atribuímos empenho, liquidação ou pagamento
          sem uma chave oficial comum.
        </p>
      </div>
      <p>
        Campo financeiro indisponível <strong>não é R$ 0</strong>. Significa que a
        fonte ainda não permite atribuir empenho, liquidação ou pagamento àquela
        autorização de Barreiras com segurança.
      </p>
      <p>
        Em 2021, o próprio catálogo oficial apresenta um link rotulado como 2021
        que aponta para o anexo de 2020. O Barreiras 360 bloqueia o ano para não
        publicar valores do exercício errado.
      </p>
      {rows === null || rows.length === 0 ? (
        <p className="transfer-coverage-unavailable">
          O diagnóstico estadual está temporariamente indisponível. As emendas e
          evidências já publicadas abaixo permanecem preservadas.
        </p>
      ) : (
        <div className="transfer-source-coverage-scroll">
          <table>
            <caption>Cobertura anual das emendas estaduais destinadas a Barreiras</caption>
            <thead>
              <tr>
                <th scope="col">Ano</th>
                <th scope="col">
                  {sourceUrl ? (
                    <a href={sourceUrl} rel="noreferrer" target="_blank">
                      Anexo oficial da LOA
                    </a>
                  ) : "Anexo oficial da LOA"}
                </th>
                <th scope="col">Execução financeira estadual</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.fiscalYear}>
                  <th scope="row">{row.fiscalYear}</th>
                  <td data-status={row.loaStatus}>
                    <strong>{stateLoaCoverageCopy(row)}</strong>
                    {row.lastAttemptedAt ? (
                      <small>
                        Conferido em {dateTimeFormatter.format(new Date(row.lastAttemptedAt))}
                      </small>
                    ) : null}
                  </td>
                  <td data-status={row.executionStatus}>
                    <strong>{stateExecutionCoverageCopy(row)}</strong>
                    {row.matchedCount !== null && row.matchedCount > 0 ? (
                      <small>
                        Pago nas ligações seguras: {formatBrlDecimal(row.paidAmount!)}
                      </small>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function CurrentFederalTransferPanel({
  transfers,
  fiscalYear,
  sourceAvailable,
  coverage,
}: Readonly<{
  transfers: readonly ParliamentaryTransfer[];
  fiscalYear: number | null;
  sourceAvailable: boolean;
  coverage: ParliamentaryTransferCoverage | null;
}>) {
  if (!sourceAvailable) {
    return (
      <section className="transfer-current-overview" aria-labelledby="current-federal-title">
        <div className="transfer-section-heading">
          <div>
            <span className="eyebrow">API federal atual</span>
            <h2 id="current-federal-title">Consulta anual temporariamente indisponível</h2>
          </div>
        </div>
        <CurrentFederalFreshness coverage={coverage} />
        <p className="transfer-empty">
          Isso é uma falha de consulta, não ausência de emendas nem valor zero.
        </p>
      </section>
    );
  }
  const summary = buildCurrentTransferCitizenSummary(transfers);
  if (summary === null) {
    return (
      <section className="transfer-current-overview" aria-labelledby="current-federal-title">
        <div className="transfer-section-heading">
          <div>
            <span className="eyebrow">API federal atual</span>
            <h2 id="current-federal-title">
              {fiscalYear === null
                ? "Nenhuma emenda atual pronta para exibição"
                : `Nenhuma emenda encontrada na API atual em ${fiscalYear}`}
            </h2>
          </div>
        </div>
        <CurrentFederalFreshness coverage={coverage} />
        <p className="transfer-empty">
          Isso não significa valor zero nem ausência de recursos. A cobertura da
          fonte e o acervo histórico podem ser conferidos logo abaixo.
        </p>
      </section>
    );
  }

  const currentTransfers = transfers.filter(
    (transfer) => transfer.fiscalYear === summary.fiscalYear,
  );
  const paidCopy = summary.paidAmount === null
    ? "Nenhum pagamento foi localizado nos endpoints consultados."
    : `${formatBrlDecimal(summary.paidAmount)} chegaram ao estágio de pagamento confirmado em ${summary.paymentFoundCount.toLocaleString("pt-BR")} emenda(s).`;

  return (
    <section className="transfer-current-overview" aria-labelledby="current-federal-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Resposta rápida · API federal atual</span>
          <h2 id="current-federal-title">
            {summary.fiscalYear}: {formatBrlDecimal(summary.destinationAmount)} destinados
          </h2>
        </div>
        <p>{summary.transferCount.toLocaleString("pt-BR")} emenda(s) encontrada(s)</p>
      </div>

      <CurrentFederalFreshness coverage={coverage} />

      <p className="transfer-current-answer">
        {paidCopy} Destinar, empenhar, pagar e executar o objeto são etapas
        diferentes; por isso, o painel não mistura esses valores.
      </p>

      <dl className="transfer-current-summary">
        <div data-tone="destination">
          <dt>Destinado nas emendas</dt>
          <dd>{formatBrlDecimal(summary.destinationAmount)}</dd>
          <span>Valor oficial atribuído às emendas encontradas.</span>
        </div>
        <div data-tone="commitment">
          <dt>Empenho localizado</dt>
          <dd>
            {summary.committedAmount === null
              ? "não encontrado"
              : formatBrlDecimal(summary.committedAmount)}
          </dd>
          <span>
            Encontrado em {summary.commitmentFoundCount.toLocaleString("pt-BR")} de {summary.transferCount.toLocaleString("pt-BR")} emenda(s).
          </span>
        </div>
        <div data-tone="paid">
          <dt>Pagamento confirmado</dt>
          <dd>
            {summary.paidAmount === null
              ? "não encontrado"
              : formatBrlDecimal(summary.paidAmount)}
          </dd>
          <span>Somente pagamentos marcados como pagos na fonte oficial.</span>
        </div>
        <div data-tone="pending">
          <dt>Sem pagamento localizado</dt>
          <dd>{formatBrlDecimal(summary.destinationWithoutPaymentAmount)}</dd>
          <span>
            Valor destinado em {summary.paymentNotFoundCount.toLocaleString("pt-BR")} emenda(s) sem pagamento localizado. Não é dívida nem perda.
          </span>
        </div>
      </dl>

      <div className="transfer-section-heading transfer-current-records-heading">
        <div>
          <span className="eyebrow">Quem destinou e para quê</span>
          <h2>Emenda por emenda</h2>
        </div>
        <p>Autor, objeto, beneficiário e documento oficial.</p>
      </div>
      <div className="transfer-card-list">
        {currentTransfers.map((transfer) => (
          <TransferCard transfer={transfer} key={transfer.externalTransferKey} />
        ))}
      </div>
    </section>
  );
}

function CurrentFederalRankingPanel({
  fiscalYear,
  result,
}: Readonly<{
  fiscalYear: number;
  result: ParliamentaryTransferRankingsResult;
}>) {
  return (
    <section
      className="transfer-ranking transfer-current-ranking"
      aria-labelledby="current-ranking-title"
    >
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Ranking de {fiscalYear} · API federal atual</span>
          <h2 id="current-ranking-title">Quem destinou recursos neste ano?</h2>
        </div>
        <p>Ordenação: pagamento confirmado; depois, valor destinado.</p>
      </div>

      {result.state === "unavailable" ? (
        <p className="transfer-empty">
          O ranking deste ano está temporariamente indisponível. Isso não significa
          ausência de emendas nem valor zero.
        </p>
      ) : (
        <div className="transfer-current-ranking-groups">
          <div>
            <h3>Parlamentares que destinaram recursos</h3>
            <p>Somente autoria individual confirmada pela fonte.</p>
            <RankingTable
              rows={result.people}
              emptyCopy={`Nenhuma autoria individual foi encontrada na API atual em ${fiscalYear}.`}
            />
          </div>
          <div>
            <h3>Comissões e bancadas</h3>
            <p>Autoria coletiva não é atribuída a um político individual.</p>
            <RankingTable
              rows={result.collectives}
              emptyCopy={`Nenhuma autoria coletiva foi encontrada na API atual em ${fiscalYear}.`}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function RankingTable({
  rows,
  emptyCopy,
}: Readonly<{
  rows: readonly ParliamentaryTransferRanking[];
  emptyCopy: string;
}>) {
  if (rows.length === 0) return <p className="transfer-empty">{emptyCopy}</p>;
  return (
    <div className="transfer-ranking-list">
      {rows.map((row) => (
        <article
          className="transfer-ranking-card"
          id={parliamentaryTransferAuthorAnchor(row.authorKey)}
          key={`${row.authorKind}:${row.authorKey}`}
        >
          <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
            {row.rankPosition}
          </span>
          <div className="transfer-ranking-name">
            <h3>{row.authorName}</h3>
            <span>{authorKindLabel(row.authorKind)}</span>
          </div>
          <dl>
            <div>
              <dt>Destinado</dt>
              <dd>{formatBrlDecimal(row.destinationAmount)}</dd>
            </div>
            <div>
              <dt>Pago confirmado</dt>
              <dd>
                {row.paidAmount === null
                  ? "não encontrado"
                  : formatBrlDecimal(row.paidAmount)}
              </dd>
            </div>
            <div>
              <dt>Emendas</dt>
              <dd>{row.amendmentCount.toLocaleString("pt-BR")}</dd>
            </div>
          </dl>
          {row.associationStatus === "approved_official_crosswalk" &&
          row.representativeSourceKind && row.representativeExternalId ? (
            <a
              className="transfer-profile-link"
              href={`/representantes#${row.representativeSourceKind}-${row.representativeExternalId}`}
            >
              Ver perfil, votos e mandato →
            </a>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function ReconciledRankingTable({
  rows,
  emptyCopy,
}: Readonly<{
  rows: readonly ReconciledParliamentaryTransferRanking[];
  emptyCopy: string;
}>) {
  if (rows.length === 0) return <p className="transfer-empty">{emptyCopy}</p>;
  return (
    <div className="transfer-ranking-list">
      {rows.map((row) => (
        <article
          className="transfer-ranking-card"
          id={`consolidado-${parliamentaryTransferAuthorAnchor(row.authorKey)}`}
          key={`reconciled:${row.authorKind}:${row.authorKey}`}
        >
          <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
            {row.rankPosition}
          </span>
          <div className="transfer-ranking-name">
            <h3>{row.authorName}</h3>
            <span>{authorKindLabel(row.authorKind)}</span>
          </div>
          <dl>
            <div>
              <dt>Destinado</dt>
              <dd>{formatBrlDecimal(row.destinationAmount)}</dd>
            </div>
            <div>
              <dt>Pago confirmado</dt>
              <dd>{row.paidAmount === null ? "não encontrado" : formatBrlDecimal(row.paidAmount)}</dd>
            </div>
            <div>
              <dt>Emendas sem duplicar</dt>
              <dd>{row.amendmentCount.toLocaleString("pt-BR")}</dd>
            </div>
          </dl>
          {row.associationStatus === "approved_official_crosswalk" &&
          row.representativeSourceKind && row.representativeExternalId ? (
            <a
              className="transfer-profile-link"
              href={`/representantes#${row.representativeSourceKind}-${row.representativeExternalId}`}
            >
              Ver perfil, votos e mandato →
            </a>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function StateLoaRankingTable({
  rows,
}: Readonly<{ rows: readonly BahiaStateLoaAmendmentRanking[] }>) {
  if (rows.length === 0) {
    return (
      <p className="transfer-empty">
        Nenhuma emenda estadual validada foi encontrada neste recorte.
      </p>
    );
  }
  const currentHouseLabel = (sourceKind: "federal" | "state") =>
    sourceKind === "federal" ? "Câmara dos Deputados" : "ALBA";
  return (
    <div className="transfer-ranking-list">
      {rows.map((row) => (
        <article
          className="transfer-ranking-card"
          id={parliamentaryTransferAuthorAnchor(row.authorKey)}
          key={`state-loa:${row.authorKey}`}
        >
          <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
            {row.rankPosition}
          </span>
          <div className="transfer-ranking-name">
            <h3>{row.authorName}</h3>
            <span>Autoria publicada no anexo da LOA da Bahia</span>
          </div>
          <dl>
            <div>
              <dt>Autorizado no orçamento</dt>
              <dd>{formatBrlDecimal(row.authorizedAmount)}</dd>
            </div>
            <div>
              <dt>Emendas encontradas</dt>
              <dd>{row.amendmentCount.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Período</dt>
              <dd>{row.firstYear === row.lastYear ? row.firstYear : `${row.firstYear}–${row.lastYear}`}</dd>
            </div>
          </dl>
          {row.associationStatus === "approved_official_crosswalk" &&
          row.representativeSourceKind && row.representativeExternalId ? (
            <div className="transfer-profile-context">
              <p>
                Perfil oficial disponível: {currentHouseLabel(row.representativeSourceKind)}.
                O perfil pode ser de outra Casa; a autoria acima continua sendo a
                publicada no anexo da LOA do ano indicado.
              </p>
              <a
                className="transfer-profile-link"
                href={`/representantes#${row.representativeSourceKind}-${row.representativeExternalId}`}
              >
                Ver perfil oficial na {currentHouseLabel(row.representativeSourceKind)} →
              </a>
            </div>
          ) : (
            <div className="transfer-profile-context">
              <p>
                Perfil atual ainda não confirmado com evidência oficial suficiente.
              </p>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function StateLoaExecutionSummaryPanel({
  summary,
}: Readonly<{ summary: StateLoaExecutionSummary | null }>) {
  if (summary === null) {
    return (
      <p className="transfer-empty">
        O cruzamento com a execução financeira estadual ainda não está disponível
        no banco público. Isso não significa que os valores sejam zero.
      </p>
    );
  }

  return (
    <aside className="transfer-reading-guide" aria-labelledby="state-loa-execution-title">
      <strong id="state-loa-execution-title">
        O que aconteceu com as {summary.totalAmendmentCount.toLocaleString("pt-BR")} emendas de {summary.fiscalYear}
      </strong>
      <p>
        Encontramos uma ligação oficial única para {summary.matchedAmendmentCount.toLocaleString("pt-BR")} emenda(s).
        Outras {summary.ambiguousAmendmentCount.toLocaleString("pt-BR")} têm chave repetida e {summary.notFoundAmendmentCount.toLocaleString("pt-BR")} não foi localizada
        na execução consultada. {summary.unavailableScopeCount > 0
          ? `${summary.unavailableScopeCount.toLocaleString("pt-BR")} permanece(m) fora do escopo disponível.`
          : "Nenhuma ficou fora do escopo deste exercício."}
      </p>
      <dl className="transfer-current-summary">
        <div data-tone="destination">
          <dt>Autorizado nas {summary.totalAmendmentCount.toLocaleString("pt-BR")} emendas</dt>
          <dd>{formatBrlDecimal(summary.authorizedTotal)}</dd>
          <span>Total da LOA; não significa pagamento.</span>
        </div>
        <div>
          <dt>Autorizado nas {summary.matchedAmendmentCount.toLocaleString("pt-BR")} ligadas</dt>
          <dd>{summary.matchedAuthorizedTotal === null ? "não disponível" : formatBrlDecimal(summary.matchedAuthorizedTotal)}</dd>
          <span>Este é o universo comparável aos estágios abaixo.</span>
        </div>
        <div>
          <dt>Empenhado nas ligações confirmadas</dt>
          <dd>{summary.committedTotal === null ? "não disponível" : formatBrlDecimal(summary.committedTotal)}</dd>
          <span>Reserva orçamentária registrada na execução estadual.</span>
        </div>
        <div>
          <dt>Liquidado nas ligações confirmadas</dt>
          <dd>{summary.liquidatedTotal === null ? "não disponível" : formatBrlDecimal(summary.liquidatedTotal)}</dd>
          <span>Despesa reconhecida após comprovação do objeto.</span>
        </div>
        <div data-tone="paid">
          <dt>Pago nas ligações confirmadas</dt>
          <dd>{summary.paidTotal === null ? "não disponível" : formatBrlDecimal(summary.paidTotal)}</dd>
          <span>Pagamento informado pela fonte estadual consultada.</span>
        </div>
      </dl>
      <p>
        Os valores de empenho, liquidação e pagamento abrangem somente as {summary.matchedAmendmentCount.toLocaleString("pt-BR")} ligações seguras.
        Por isso, não devem ser comparados diretamente com o total autorizado das {summary.totalAmendmentCount.toLocaleString("pt-BR")} emendas.
      </p>
    </aside>
  );
}

function StateLoaExecutionGroupPanel({
  groups,
}: Readonly<{ groups: readonly StateLoaExecutionGroup[] | null }>) {
  if (groups === null) {
    return (
      <p className="transfer-empty">
        O detalhamento de execuções agregadas está temporariamente indisponível.
        Os valores das emendas individuais continuam sem atribuição automática.
      </p>
    );
  }
  if (groups.length === 0) return null;

  return (
    <section aria-labelledby="state-loa-group-execution-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Leitura complementar da execução</span>
          <h3 id="state-loa-group-execution-title">
            Execução disponível apenas para o grupo
          </h3>
        </div>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Por que estes valores aparecem separados?</strong>
        <p>
          Em cada grupo abaixo, todas as linhas da chave oficial da LOA são
          destinadas a Barreiras. A fonte estadual publicou uma única execução
          para o conjunto: os valores podem ser atribuídos ao grupo, mas não
          podem ser repartidos entre as emendas. Por isso, eles não entram nos
          valores individuais nem no ranking de execução.
        </p>
      </aside>
      <div className="transfer-card-list">
        {groups.map((group) => (
          <article
            className="transfer-card"
            key={`${group.fiscalYear}:${group.authorExternalCode}:${group.agencyCode}:${group.budgetUnitCode}:${group.actionCode}`}
          >
            <div className="transfer-card-heading">
              <div>
                <span className="transfer-card-kind">
                  LOA da Bahia · {group.fiscalYear} · execução agregada
                </span>
                <h3>{group.authorName}</h3>
                <p>
                  Emendas {group.amendmentNumbers.join(", ")} · ação {group.actionCode}
                </p>
              </div>
              <span className="transfer-status">
                grupo de {group.amendmentCount.toLocaleString("pt-BR")} emendas
              </span>
            </div>
            <dl className="transfer-stage-grid">
              <div>
                <dt>Autorizado nas emendas do grupo</dt>
                <dd>{formatBrlDecimal(group.authorizedTotal)}</dd>
                <span>Soma das autorizações destinadas a Barreiras.</span>
              </div>
              <div>
                <dt>Dotação inicial da chave estadual</dt>
                <dd>{formatBrlDecimal(group.initialBudgetAmount)}</dd>
                <span>Valor agregado publicado na fonte de execução.</span>
              </div>
              <div>
                <dt>Dotação atual da chave estadual</dt>
                <dd>{formatBrlDecimal(group.currentBudgetAmount)}</dd>
                <span>Pode mudar após alterações orçamentárias.</span>
              </div>
              <div>
                <dt>Empenhado no grupo</dt>
                <dd>{formatBrlDecimal(group.committedAmount)}</dd>
                <span>Não permite identificar quanto pertence a cada emenda.</span>
              </div>
              <div>
                <dt>Liquidado no grupo</dt>
                <dd>{formatBrlDecimal(group.liquidatedAmount)}</dd>
                <span>Valor agregado reconhecido pela fonte estadual.</span>
              </div>
              <div data-tone="paid">
                <dt>Pago no grupo</dt>
                <dd>{formatBrlDecimal(group.paidAmount)}</dd>
                <span>Valor agregado, sem rateio por emenda.</span>
              </div>
            </dl>
            <p className="transfer-card-note">
              Chave oficial: órgão {group.agencyCode}, unidade {group.budgetUnitCode},
              ação {group.actionCode}. Código da execução: {group.executionCode}.
            </p>
            <details className="transfer-details">
              <summary>Conferir integridade e fonte da execução do grupo</summary>
              <p>
                Coletada em {dateTimeFormatter.format(new Date(group.executionSourceCollectedAt))}.<br />
                Hash do arquivo: <code>{group.executionSourceArtifactSha256}</code><br />
                Hash da evidência: <code>{group.executionEvidenceSha256}</code>
              </p>
              <a
                className="transfer-source-link"
                href={group.executionSourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                Abrir fonte oficial da execução →
              </a>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}

function StateLoaAmendmentCard({
  amendment,
  execution,
}: Readonly<{
  amendment: BahiaStateLoaAmendment;
  execution: StateLoaExecutionRecord | null;
}>) {
  const executionCopy = execution === null
    ? null
    : stateLoaExecutionStatusCopy(execution);
  const executionConfirmed = execution?.executionStatus === "execution_confirmed";
  return (
    <article className="transfer-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">LOA da Bahia · {amendment.fiscalYear}</span>
          <h3>{amendment.authorName}</h3>
          <p>Emenda {amendment.amendmentNumber} · página {amendment.pageNumber}</p>
        </div>
        <span className="transfer-status">
          {executionCopy?.label ?? "autorizada no orçamento"}
        </span>
      </div>
      <p className="transfer-object">{amendment.officialDescription}</p>
      <dl className="transfer-stage-grid">
        <div>
          <dt>Valor autorizado</dt>
          <dd>{formatBrlDecimal(amendment.authorizedAmount)}</dd>
          <span>Dotação aprovada na LOA; não é confirmação de pagamento.</span>
        </div>
        <div>
          <dt>Unidade orçamentária</dt>
          <dd>{amendment.budgetUnitCode ?? "não informada na linha"}</dd>
          <span>Ação {amendment.actionCode ?? "não informada"}</span>
        </div>
        <div>
          <dt>Órgão</dt>
          <dd>{amendment.agencyCode ?? "não informado na linha"}</dd>
          <span>Anexo {amendment.annexCode ?? "não informado"}</span>
        </div>
      </dl>
      {executionCopy ? (
        <aside className="transfer-reading-guide" data-tone={executionCopy.tone}>
          <strong>{executionCopy.label}</strong>
          <p>{executionCopy.explanation}</p>
          {executionConfirmed ? (
            <dl className="transfer-stage-grid">
              <div><dt>Autorizado</dt><dd>{formatBrlDecimal(execution.authorizedAmount)}</dd><span>Valor aprovado na LOA.</span></div>
              <div><dt>Empenhado</dt><dd>{formatBrlDecimal(execution.committedAmount!)}</dd><span>Reserva registrada na execução.</span></div>
              <div><dt>Liquidado</dt><dd>{formatBrlDecimal(execution.liquidatedAmount!)}</dd><span>Despesa reconhecida pela fonte.</span></div>
              <div><dt>Pago</dt><dd>{formatBrlDecimal(execution.paidAmount!)}</dd><span>Pagamento informado pela fonte.</span></div>
            </dl>
          ) : null}
        </aside>
      ) : null}
      <details className="transfer-details">
        <summary>Trecho exato que sustenta este registro</summary>
        <p>{amendment.evidenceText}</p>
        <p>
          Hash do PDF: <code>{amendment.sourceArtifactSha256}</code><br />
          Hash do trecho: <code>{amendment.evidenceSha256}</code>
        </p>
      </details>
      <a className="transfer-source-link" href={amendment.sourceUrl} rel="noreferrer" target="_blank">
        Abrir anexo oficial da LOA →
      </a>
      {executionConfirmed && execution.executionSourceUrl ? (
        <details className="transfer-details">
          <summary>Conferir a fonte da execução estadual</summary>
          <p>
            Coletada em {dateTimeFormatter.format(new Date(execution.executionSourceCollectedAt!))}.<br />
            Hash do arquivo: <code>{execution.executionSourceArtifactSha256}</code><br />
            Hash da evidência: <code>{execution.executionEvidenceSha256}</code>
          </p>
          <a className="transfer-source-link" href={execution.executionSourceUrl} rel="noreferrer" target="_blank">
            Abrir fonte oficial da execução →
          </a>
        </details>
      ) : null}
    </article>
  );
}

function StateLoaPanel({
  ranking,
  amendments,
  execution,
  executionSummary,
  executionGroups,
  totalCount,
  catalogCount,
  availableAuthors,
  filters,
  page,
  pageSize,
  selectedFiscalYear,
  availableFiscalYears,
  coverage,
  executionArchiveCoverage,
}: Readonly<{
  ranking: readonly BahiaStateLoaAmendmentRanking[] | null;
  amendments: readonly BahiaStateLoaAmendment[] | null;
  execution: readonly StateLoaExecutionRecord[] | null;
  executionSummary: StateLoaExecutionSummary | null;
  executionGroups: readonly StateLoaExecutionGroup[] | null;
  totalCount: number;
  catalogCount: number;
  availableAuthors: readonly StateLoaStudyAuthor[];
  filters: StateLoaStudyFilters;
  page: number;
  pageSize: number;
  selectedFiscalYear: number;
  availableFiscalYears: readonly number[];
  coverage: readonly StateAmendmentSourceCoverage[] | null;
  executionArchiveCoverage: readonly BahiaStateExecutionCoverage[] | null;
}>) {
  const executionByEvidence = new Map(
    (execution ?? []).map((row) => [row.loaEvidenceSha256, row]),
  );
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize));
  const hasFilters = Boolean(
    filters.authorKey || filters.executionStatus || filters.query,
  );
  const clearFiltersHref = stateLoaStudyPageHref(selectedFiscalYear, 1);
  return (
    <section className="transfer-ranking" aria-labelledby="state-loa-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">
            Recursos estaduais · {selectedFiscalYear}
          </span>
          <h2 id="state-loa-title">Emendas estaduais autorizadas na LOA</h2>
        </div>
        <p>Fonte: anexos oficiais da Secretaria do Planejamento da Bahia.</p>
      </div>
      <form
        className="transfer-year-filter"
        method="get"
        aria-label="Filtrar emendas estaduais por ano"
      >
        <input type="hidden" name="origem" value="estadual" />
        <div>
          <label htmlFor="state-loa-year">Ano da LOA estadual</label>
          <select
            id="state-loa-year"
            name="ano"
            defaultValue={selectedFiscalYear}
          >
            {availableFiscalYears.map((year) => (
              <option value={year} key={year}>{year}</option>
            ))}
          </select>
        </div>
        <button type="submit">Ver este ano</button>
        <p>
          Resumo de {selectedFiscalYear}: ranking, emendas e situação da execução
          usam o mesmo exercício, sem somar anos diferentes.
        </p>
      </form>
      <form
        className="transfer-year-filter transfer-document-filters"
        method="get"
        aria-label="Pesquisar emendas estaduais"
      >
        <input type="hidden" name="origem" value="estadual" />
        <input type="hidden" name="ano" value={selectedFiscalYear} />
        <div>
          <label htmlFor="state-loa-query">Parlamentar, número ou objeto</label>
          <input
            id="state-loa-query"
            name="estadual_q"
            type="search"
            defaultValue={filters.query ?? ""}
            maxLength={100}
            placeholder="Ex.: ônibus escolar ou 5724"
          />
        </div>
        <div>
          <label htmlFor="state-loa-author">Parlamentar</label>
          <select
            id="state-loa-author"
            name="estadual_autor"
            defaultValue={filters.authorKey ?? ""}
          >
            <option value="">Todos os parlamentares</option>
            {availableAuthors.map((author) => (
              <option value={author.authorKey} key={author.authorKey}>
                {author.authorName}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="state-loa-status">Situação da execução</label>
          <select
            id="state-loa-status"
            name="estadual_situacao"
            defaultValue={filters.executionStatus ?? ""}
          >
            <option value="">Todas as situações</option>
            <option value="execution_confirmed">Execução encontrada</option>
            <option value="ambiguous_official_key">Ligação ambígua</option>
            <option value="not_found_in_execution_source">Não encontrada na execução</option>
            <option value="official_link_key_unavailable">Fonte sem chave de cruzamento</option>
            <option value="scope_not_available">Cruzamento indisponível</option>
          </select>
        </div>
        <button type="submit">Pesquisar emendas</button>
        {hasFilters ? (
          <a className="filter-clear" href={clearFiltersHref}>Limpar filtros</a>
        ) : null}
        <p>
          {totalCount.toLocaleString("pt-BR")} de {catalogCount.toLocaleString("pt-BR")} emenda(s)
          correspondem a este recorte. O ranking e os totais acima continuam mostrando
          o exercício completo.
        </p>
      </form>
      <aside className="transfer-reading-guide">
        <strong>O que estes valores realmente dizem</strong>
        <p>
          “Autorizado” significa que a emenda entrou no orçamento estadual. Isso
          não significa dinheiro pago, transferido a Barreiras ou obra executada.
          No exercício selecionado, os estágios aparecem somente quando a LOA pôde
          ser ligada a
          uma única linha da execução estadual. Ligações ambíguas ficam sem valor.
        </p>
        <p>
          Nos anos anteriores, os documentos encontrados não trazem todos os
          identificadores necessários para ligar cada autorização a uma linha
          exclusiva da execução. Nesses casos, mostramos a limitação em cada
          emenda e não inventamos empenho, liquidação ou pagamento.
        </p>
        <p>
          A ordem abaixo usa somente soma decimal em SQL. Não é nota de desempenho
          nem avaliação política; mostra quem aparece com maior valor autorizado
          nos anexos municipais encontrados.
        </p>
      </aside>
      <details className="transfer-methodology">
        <summary>Como a Bahia relaciona os dados</summary>
        <p>
          O arquivo de execução não publica município. Ele liga despesas,
          liquidações e pagamentos por códigos internos do FIPLAN. Por isso, o
          Barreiras 360 usa os anexos da LOA para identificar as autorizações de
          Barreiras e só mostra execução quando os identificadores oficiais formam
          uma ligação única. Ausência de ligação não significa valor zero.
        </p>
        <p>
          <a
            href="https://dados.ba.gov.br/dataset/1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/f463ff7d-569c-4b48-b1d3-c80f017779df/download/emendas-parlamentares-relacionamento_views.png"
            rel="noreferrer"
            target="_blank"
          >
            Abrir diagrama oficial das relações ↗
          </a>
          {" · "}
          <a
            href="https://www.transparencia.ba.gov.br/EmendasParlamentares/PainelEmendasParlamentares"
            rel="noreferrer"
            target="_blank"
          >
            Consultar o painel oficial da Bahia ↗
          </a>
        </p>
      </details>
      <BahiaStateExecutionCoveragePanel rows={executionArchiveCoverage} />
      <StateAmendmentSourceCoveragePanel rows={coverage} />
      <StateLoaExecutionSummaryPanel summary={executionSummary} />
      <StateLoaExecutionGroupPanel groups={executionGroups} />
      {ranking === null ? (
        <p className="transfer-empty">
          A projeção estadual ainda não está disponível no banco público. Isso não
          significa ausência de emendas.
        </p>
      ) : <StateLoaRankingTable rows={ranking} />}
      {amendments && amendments.length > 0 ? (
        <details
          className="transfer-methodology"
          id="emendas-estaduais"
          open={page > 1 || hasFilters}
        >
          <summary>
            Conferir emendas, objetos e fontes · {amendments.length.toLocaleString("pt-BR")} nesta página de {totalCount.toLocaleString("pt-BR")}
          </summary>
          <div className="transfer-card-list">
            {amendments.map((amendment) => (
              <StateLoaAmendmentCard
                amendment={amendment}
                execution={executionByEvidence.get(amendment.evidenceSha256) ?? null}
                key={`${amendment.fiscalYear}:${amendment.amendmentNumber}:${amendment.evidenceSha256}`}
              />
            ))}
          </div>
          {totalCount > pageSize ? (
            <nav className="legislative-pagination" aria-label="Paginação das emendas estaduais">
              {page > 1 ? (
                <a href={stateLoaStudyPageHref(selectedFiscalYear, page - 1, filters)}>
                  ← Emendas anteriores
                </a>
              ) : <span />}
              <span>Página {page} de {pageCount.toLocaleString("pt-BR")}</span>
              {page < pageCount ? (
                <a href={stateLoaStudyPageHref(selectedFiscalYear, page + 1, filters)}>
                  Próximas emendas →
                </a>
              ) : <span />}
            </nav>
          ) : null}
        </details>
      ) : hasFilters ? (
        <p className="transfer-empty" id="emendas-estaduais">
          Nenhuma emenda corresponde aos filtros informados. Isso não significa que
          o exercício não tenha emendas; limpe os filtros para consultar o acervo anual.
        </p>
      ) : null}
    </section>
  );
}

const CGU_LINK_STATUS_COPY: Readonly<Record<
  CguFederalAmendment["transferegovLinkStatus"],
  string
>> = {
  code_unavailable:
    "A fonte não publicou o código oficial desta emenda; o vínculo com o Transferegov não pode ser conferido.",
  not_found_in_transferegov:
    "Não localizada nas bases preservadas do Transferegov. As coberturas das fontes diferem; isso não é erro.",
  matched_transferegov_unique:
    "Também aparece no Transferegov com o mesmo código oficial. Os valores não são somados entre fontes.",
  conflict_non_unique_transferegov:
    "O código oficial aparece mais de uma vez no Transferegov; o vínculo fica suspenso para auditoria.",
};

function CguRankingList({
  rows,
  scopeLabel,
  showInvestigationLink = false,
}: Readonly<{
  rows: readonly CguFederalAmendmentRanking[];
  scopeLabel: string;
  showInvestigationLink?: boolean;
}>) {
  if (rows.length === 0) {
    return (
      <p className="transfer-empty">
        Nenhuma autoria {scopeLabel} identificada pela fonte neste recorte.
      </p>
    );
  }
  return (
    <div className="transfer-ranking-list">
      {rows.map((row) => (
        <article
          className="transfer-ranking-card"
          id={parliamentaryTransferAuthorAnchor(row.authorKey)}
          key={`cgu:${row.authorKind}:${row.authorKey}`}
        >
          <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
            {row.rankPosition}
          </span>
          <div className="transfer-ranking-name">
            <h3>{row.authorName}</h3>
            <span>Autoria publicada no arquivo aberto da CGU</span>
          </div>
          <dl>
            <div>
              <dt>Empenhado</dt>
              <dd>{formatBrlDecimal(row.committedAmount)}</dd>
            </div>
            <div>
              <dt>Pago efetivo</dt>
              <dd>{formatBrlDecimal(row.effectivePaidAmount)}</dd>
            </div>
            <div>
              <dt>Emendas encontradas</dt>
              <dd>{row.amendmentCount.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Período</dt>
              <dd>{row.firstYear === row.lastYear ? row.firstYear : `${row.firstYear}–${row.lastYear}`}</dd>
            </div>
          </dl>
          {showInvestigationLink ? (
            <a className="transfer-ranking-action" href={cguExecutionAuthorHref(row.authorKey)}>
              Ver linhas oficiais deste parlamentar
            </a>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function CguAmendmentCard({
  amendment,
}: Readonly<{ amendment: CguFederalAmendment }>) {
  return (
    <article className="transfer-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">
            Execução federal (CGU) · {amendment.fiscalYear}
          </span>
          <h3>{amendment.authorName}</h3>
          <p>
            {amendment.hasOfficialCode
              ? `Emenda ${amendment.amendmentCode}`
              : "Código da emenda não publicado pela fonte"}
            {" · "}{amendment.amendmentType}
          </p>
        </div>
        <span className="transfer-status">{amendment.functionName}</span>
      </div>
      <p className="transfer-object">
        {amendment.actionName} · {amendment.programName}
      </p>
      <dl className="transfer-stage-grid">
        <div>
          <dt>Empenhado</dt>
          <dd>{formatBrlDecimal(amendment.committedAmount)}</dd>
          <span>Reserva registrada no orçamento federal.</span>
        </div>
        <div>
          <dt>Liquidado</dt>
          <dd>{formatBrlDecimal(amendment.liquidatedAmount)}</dd>
          <span>Despesa reconhecida pela fonte.</span>
        </div>
        <div>
          <dt>Pago no exercício</dt>
          <dd>{formatBrlDecimal(amendment.paidAmount)}</dd>
          <span>Pagamento dentro do próprio ano.</span>
        </div>
        <div>
          <dt>Restos pagos</dt>
          <dd>{formatBrlDecimal(amendment.outstandingPaidAmount)}</dd>
          <span>Pagamento de anos seguintes (restos a pagar).</span>
        </div>
        <div>
          <dt>Pago efetivo</dt>
          <dd>{formatBrlDecimal(amendment.effectivePaidAmount)}</dd>
          <span>Único total derivado: pago no exercício + restos pagos.</span>
        </div>
      </dl>
      <aside className="transfer-reading-guide">
        <strong>Vínculo com o Transferegov</strong>
        <p>{CGU_LINK_STATUS_COPY[amendment.transferegovLinkStatus]}</p>
      </aside>
      <details className="transfer-details">
        <summary>Evidência oficial desta linha</summary>
        <p>
          Linha {amendment.sourceRowNumber.toLocaleString("pt-BR")} do arquivo
          nacional, coletada em {dateTimeFormatter.format(new Date(amendment.collectedAt))}.<br />
          Hash do ZIP oficial: <code>{amendment.artifactSha256}</code>
        </p>
      </details>
      <a className="transfer-source-link" href={amendment.sourceUrl} rel="noreferrer" target="_blank">
        Abrir arquivo oficial da CGU →
      </a>
    </article>
  );
}

const CGU_DOCUMENT_STAGE_COPY: Readonly<Record<
  CguFederalAmendmentDocument["expenseStage"],
  string
>> = {
  commitment: "Empenho",
  liquidation: "Liquidação",
  payment: "Pagamento",
};

type SearchParamValue = string | readonly string[] | undefined;
type ResolvedCguDocumentFilters = CguFederalAmendmentDocumentFilters &
  Readonly<{ page: number }>;

function singleSearchParam(value: SearchParamValue): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  return typeof candidate === "string" ? candidate.trim() : null;
}

function resolveCguDocumentFilters(params: Readonly<{
  documento_pagina?: SearchParamValue;
  documento_ano?: SearchParamValue;
  documento_autor?: SearchParamValue;
  documento_etapa?: SearchParamValue;
  documento_q?: SearchParamValue;
}>): ResolvedCguDocumentFilters {
  const pageValue = Number(singleSearchParam(params.documento_pagina));
  const yearValue = Number(singleSearchParam(params.documento_ano));
  const authorValue = singleSearchParam(params.documento_autor);
  const stageValue = singleSearchParam(params.documento_etapa);
  const queryValue = singleSearchParam(params.documento_q);
  return {
    page: Number.isInteger(pageValue) && pageValue >= 1 && pageValue <= 201
      ? pageValue
      : 1,
    archiveYear: Number.isInteger(yearValue) &&
        yearValue >= 2021 && yearValue <= 2100
      ? yearValue
      : null,
    authorKey: authorValue && authorValue.length <= 200 ? authorValue : null,
    expenseStage: stageValue === "commitment" ||
        stageValue === "liquidation" || stageValue === "payment"
      ? stageValue
      : null,
    query: queryValue && queryValue.length <= 100 ? queryValue : null,
  };
}

function cguDocumentPageHref(
  filters: ResolvedCguDocumentFilters,
  page: number,
  preservedAuthor: string | null,
  preservedYear: number | null,
): string {
  const query = new URLSearchParams({ origem: "federal-execucao" });
  if (preservedAuthor) query.set("autor", preservedAuthor);
  if (preservedYear) query.set("ano", String(preservedYear));
  if (filters.archiveYear) {
    query.set("documento_ano", String(filters.archiveYear));
  }
  if (filters.authorKey) query.set("documento_autor", filters.authorKey);
  if (filters.expenseStage) {
    query.set("documento_etapa", filters.expenseStage);
  }
  if (filters.query) query.set("documento_q", filters.query);
  if (page > 1) query.set("documento_pagina", String(page));
  return `/recursos?${query.toString()}#cgu-documents-title`;
}

function CguDocumentMovementPanel({
  result,
  filters,
  preservedAuthor,
  preservedYear,
}: Readonly<{
  result: CguFederalAmendmentDocumentsResult;
  filters: ResolvedCguDocumentFilters;
  preservedAuthor: string | null;
  preservedYear: number | null;
}>) {
  if (result.state === "unavailable") {
    return (
      <aside className="transfer-reading-guide">
        <strong>Documentos anuais ainda não disponíveis</strong>
        <p>
          O detalhamento por empenho, liquidação e pagamento ainda não
          respondeu. Isso não significa ausência de movimentação nem valor zero.
        </p>
      </aside>
    );
  }
  const pageCount = Math.max(1, Math.ceil(result.totalCount / result.pageSize));
  const clearHref = cguDocumentPageHref(
    {
      page: 1,
      archiveYear: null,
      authorKey: null,
      expenseStage: null,
      query: null,
    },
    1,
    preservedAuthor,
    preservedYear,
  );
  return (
    <section className="transfer-document-movements" aria-labelledby="cgu-documents-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Comprovantes da execução</span>
          <h2 id="cgu-documents-title">Movimentações por documento oficial</h2>
        </div>
        <p>
          {result.documents.length.toLocaleString("pt-BR")} nesta página ·{" "}
          {result.totalCount.toLocaleString("pt-BR")} no recorte ·{" "}
          {result.catalogCount.toLocaleString("pt-BR")} no catálogo documental
        </p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Como ler sem confundir os anos</strong>
        <p>
          O ano do documento pode ser diferente do ano da emenda. Uma emenda de
          2022, por exemplo, pode ter pagamento registrado em 2024. Cada cartão
          informa as duas datas e a fase financeira publicada pela CGU.
        </p>
        <p>
          Os valores desta série não são somados ao retrato agregado da CGU,
          ao Transferegov ou a qualquer fonte estadual. Ela serve para mostrar
          quando e por qual documento o dinheiro avançou.
        </p>
      </aside>
      <form
        className="transfer-year-filter transfer-document-filters"
        method="get"
        aria-label="Filtrar documentos federais por ano, autoria, fase e texto"
      >
        <input type="hidden" name="origem" value="federal-execucao" />
        {preservedAuthor ? (
          <input type="hidden" name="autor" value={preservedAuthor} />
        ) : null}
        {preservedYear ? (
          <input type="hidden" name="ano" value={preservedYear} />
        ) : null}
        <div>
          <label htmlFor="cgu-document-query">Buscar nos documentos</label>
          <input
            defaultValue={filters.query ?? ""}
            id="cgu-document-query"
            maxLength={100}
            name="documento_q"
            placeholder="Autor, emenda, favorecido, órgão ou objeto"
            type="search"
          />
        </div>
        <div>
          <label htmlFor="cgu-document-year">Ano do documento</label>
          <select
            defaultValue={filters.archiveYear?.toString() ?? ""}
            id="cgu-document-year"
            name="documento_ano"
          >
            <option value="">Todos os anos</option>
            {result.availableYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="cgu-document-author">Autoria publicada</label>
          <select
            defaultValue={filters.authorKey ?? ""}
            id="cgu-document-author"
            name="documento_autor"
          >
            <option value="">Todos os autores</option>
            {result.availableAuthors.map((author) => (
              <option key={author.authorKey} value={author.authorKey}>
                {author.authorName}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="cgu-document-stage">Fase do documento</label>
          <select
            defaultValue={filters.expenseStage ?? ""}
            id="cgu-document-stage"
            name="documento_etapa"
          >
            <option value="">Todas as fases</option>
            {result.availableStages.map((stage) => (
              <option key={stage} value={stage}>
                {CGU_DOCUMENT_STAGE_COPY[stage]}
              </option>
            ))}
          </select>
        </div>
        <button type="submit">Aplicar filtros</button>
        <a href={clearHref}>Limpar documentos</a>
        <p>
          Os filtros são aplicados no servidor sobre todo o acervo documental.
          O ranking de autoria permanece calculado sobre a série completa.
        </p>
      </form>
      {result.ranking.length > 0 ? (
        <details className="transfer-methodology">
          <summary>Ver autoria por pagamentos documentados</summary>
          <div className="transfer-ranking-list">
            {result.ranking.map((row) => (
              <article className="transfer-ranking-card" key={`cgu-document:${row.authorKey}`}>
                <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
                  {row.rankPosition}
                </span>
                <div className="transfer-ranking-name">
                  <h3>{row.authorName}</h3>
                  <span>{authorKindLabel(row.authorKind)}</span>
                </div>
                <dl>
                  <div><dt>Pago nos documentos</dt><dd>{formatBrlDecimal(row.paidAmount)}</dd></div>
                  <div><dt>Empenhado nos documentos</dt><dd>{formatBrlDecimal(row.committedAmount)}</dd></div>
                  <div><dt>Emendas</dt><dd>{row.amendmentCount}</dd></div>
                  <div><dt>Documentos</dt><dd>{row.documentCount}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        </details>
      ) : null}
      <section aria-labelledby="cgu-document-results-title">
        <h3 id="cgu-document-results-title">
          Documentos, favorecidos e evidências
        </h3>
        {result.documents.length === 0 ? (
          <p className="transfer-empty">
            A fonte foi consultada, mas ainda não há documento territorializado
            para Barreiras neste recorte. Isso não significa valor zero.
          </p>
        ) : (
          <div className="transfer-card-list">
            {result.documents.map((document) => (
              <article
                className="transfer-card"
                key={`${document.archiveYear}:${document.documentCode}:${document.sourceRowNumber}`}
              >
                <div className="transfer-card-heading">
                  <div>
                    <span className="transfer-card-kind">
                      {CGU_DOCUMENT_STAGE_COPY[document.expenseStage]} em {formatDate(document.documentDate)}
                    </span>
                    <h3>{document.authorName}</h3>
                    <p>Emenda {document.amendmentCode} · ano da emenda {document.amendmentYear}</p>
                  </div>
                  <span className="transfer-status">Documento de {document.archiveYear}</span>
                </div>
                <p className="transfer-object">
                  {document.citizenLanguage ?? document.actionName}
                </p>
                <dl className="transfer-stage-grid">
                  <div>
                    <dt>Empenhado nesta linha</dt>
                    <dd>{formatBrlDecimal(document.committedAmount)}</dd>
                  </div>
                  <div>
                    <dt>Pago nesta linha</dt>
                    <dd>{formatBrlDecimal(document.paidAmount)}</dd>
                  </div>
                  <div>
                    <dt>Favorecido</dt>
                    <dd>{document.beneficiaryName}</dd>
                  </div>
                  <div>
                    <dt>Órgão federal</dt>
                    <dd>{document.agencyName}</dd>
                  </div>
                </dl>
                <details className="transfer-details">
                  <summary>Evidência e identificação do documento</summary>
                  <p>
                    Documento <code>{document.documentCode}</code> · linha {document.sourceRowNumber.toLocaleString("pt-BR")} do arquivo anual.<br />
                    Hash do ZIP oficial: <code>{document.artifactSha256}</code>
                  </p>
                </details>
                <a className="transfer-source-link" href={document.sourceUrl} rel="noreferrer" target="_blank">
                  Abrir arquivo oficial da CGU →
                </a>
              </article>
            ))}
          </div>
        )}
        {result.totalCount > result.pageSize ? (
          <nav className="legislative-pagination" aria-label="Paginação dos documentos federais">
            {result.page > 1 ? (
              <a href={cguDocumentPageHref(
                filters,
                result.page - 1,
                preservedAuthor,
                preservedYear,
              )}>← Mais recentes</a>
            ) : <span />}
            <span>Página {result.page} de {pageCount.toLocaleString("pt-BR")}</span>
            {result.page < pageCount ? (
              <a href={cguDocumentPageHref(
                filters,
                result.page + 1,
                preservedAuthor,
                preservedYear,
              )}>Documentos anteriores →</a>
            ) : <span />}
          </nav>
        ) : null}
      </section>
    </section>
  );
}

function CguFederalExecutionPanel({
  result,
  documentResult,
  documentFilters,
  coverage,
  requestedAuthor,
  requestedYear,
}: Readonly<{
  result: CguFederalAmendmentsResult;
  documentResult: CguFederalAmendmentDocumentsResult;
  documentFilters: ResolvedCguDocumentFilters;
  coverage: readonly FederalTransferSourceCoverage[];
  requestedAuthor: string | readonly string[] | undefined;
  requestedYear: string | readonly string[] | undefined;
}>) {
  if (result.state === "unavailable") {
    return (
      <section className="transfer-ranking" aria-labelledby="cgu-execution-title">
        <div className="transfer-section-heading">
          <div>
            <span className="eyebrow">Execução federal regionalizada</span>
            <h2 id="cgu-execution-title">Série da CGU em preparação</h2>
          </div>
        </div>
        <p className="transfer-empty">
          A série do Portal da Transparência ainda não está disponível no banco
          público. Isso é uma limitação de consulta ou de coleta, nunca prova de
          ausência de emendas.
        </p>
      </section>
    );
  }
  const filters = resolveCguExecutionFilters(
    requestedAuthor,
    requestedYear,
    result.amendments,
  );
  const filteredAmendments = filterCguExecutionAmendments(
    result.amendments,
    filters,
  );
  const authorCoverage = buildCguAuthorCoverageSummary(
    result.amendments,
    coverage,
    filters.authorKey,
  );
  const availableYears = [...new Set(
    result.amendments.map((amendment) => amendment.fiscalYear),
  )].sort((left, right) => right - left);
  const availablePeople = [...result.people]
    .sort((left, right) => left.authorName.localeCompare(right.authorName, "pt-BR"));
  return (
    <section className="transfer-ranking" aria-labelledby="cgu-execution-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Execução federal regionalizada</span>
          <h2 id="cgu-execution-title">
            Emendas executadas em Barreiras segundo a CGU
          </h2>
        </div>
        <p>Fonte: arquivo aberto de emendas do Portal da Transparência.</p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>O que esta série realmente diz</strong>
        <p>
          O município nesta fonte indica onde a execução orçamentária foi
          regionalizada. Não prova, sozinho, repasse direto à Prefeitura,
          conclusão de obra ou regularidade do gasto.
        </p>
        <p>
          Empenhado, liquidado, pago no exercício e restos a pagar são etapas
          diferentes e nunca são somados entre si. O único total derivado é o
          pago efetivo: pago no exercício mais restos a pagar pagos. Anos
          ausentes significam “não encontrado nesta fonte”, nunca valor zero.
        </p>
        <p>
          Emendas que também existem no Transferegov são apenas rotuladas pelo
          código oficial — os valores de cada fonte permanecem separados, sem
          dupla contagem. Para convênios e transferências pactuados com a
          cidade,{" "}
          <a href="/recursos?origem=federal-historico">
            veja as abas de convênios do Transferegov →
          </a>
        </p>
      </aside>
      <form
        className="transfer-year-filter transfer-execution-filters"
        method="get"
        aria-label="Filtrar execução federal por parlamentar e ano"
      >
        <input type="hidden" name="origem" value="federal-execucao" />
        <div>
          <label htmlFor="cgu-author-filter">Parlamentar</label>
          <select
            defaultValue={filters.authorKey ?? ""}
            id="cgu-author-filter"
            name="autor"
          >
            <option value="">Todos os autores individuais</option>
            {availablePeople.map((person) => (
              <option key={person.authorKey} value={person.authorKey}>
                {person.authorName}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="cgu-year-filter">Ano da execução</label>
          <select
            defaultValue={filters.fiscalYear?.toString() ?? ""}
            id="cgu-year-filter"
            name="ano"
          >
            <option value="">Todos os anos</option>
            {availableYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
        <button type="submit">Aplicar filtros</button>
        <a href="/recursos?origem=federal-execucao">Limpar</a>
        <p>
          <strong>{cguExecutionResultCountCopy(filteredAmendments.length)}</strong>{" "}
          O ranking abaixo permanece calculado sobre todo o acervo desta fonte.
        </p>
      </form>
      {authorCoverage ? (
        <CguAuthorCoverageCard summary={authorCoverage} />
      ) : null}
      <aside className="transfer-transition-note">
        <strong>Como tratamos 2023</strong>
        <p>
          2023 é um ano de transição entre duas legislaturas. A emenda continua
          visível nesta execução anual, com autor, valores e fonte, mas não
          entra no ranking por legislatura para evitar atribuição ao mandato
          errado.
        </p>
      </aside>
      <h3>Autoria individual</h3>
      <CguRankingList
        rows={result.people}
        scopeLabel="individual"
        showInvestigationLink
      />
      <h3>Comissões e bancadas</h3>
      <CguRankingList rows={result.collectives} scopeLabel="coletiva" />
      <CguDocumentMovementPanel
        filters={documentFilters}
        preservedAuthor={filters.authorKey}
        preservedYear={filters.fiscalYear}
        result={documentResult}
      />
      {filteredAmendments.length > 0 ? (
        <details className="transfer-methodology">
          <summary>
            Conferir as {filteredAmendments.length.toLocaleString("pt-BR")} linhas oficiais, estágios e evidências
          </summary>
          <div className="transfer-card-list">
            {filteredAmendments.map((amendment) => (
              <CguAmendmentCard
                amendment={amendment}
                key={`${amendment.fiscalYear}:${amendment.amendmentCode}:${amendment.sourceRowNumber}`}
              />
            ))}
          </div>
        </details>
      ) : (
        <p className="transfer-empty">
          Nenhuma linha combina os filtros selecionados. Isso não altera nem
          apaga o acervo oficial; limpe um dos filtros para ampliar a consulta.
        </p>
      )}
    </section>
  );
}

function yearList(years: readonly number[]): string {
  return new Intl.ListFormat("pt-BR", {
    style: "long",
    type: "conjunction",
  }).format(years.map(String));
}

function CguAuthorCoverageCard({
  summary,
}: Readonly<{ summary: CguAuthorCoverageSummary }>) {
  return (
    <aside
      className="transfer-author-audit"
      aria-label={`Cobertura federal encontrada para ${summary.authorName}`}
    >
      <div className="transfer-author-audit-heading">
        <div>
          <span className="eyebrow">O que encontramos para este parlamentar</span>
          <h3>{summary.authorName}</h3>
        </div>
        <span>Fonte territorial da CGU</span>
      </div>
      <dl>
        <div>
          <dt>Registros atribuídos</dt>
          <dd>{summary.recordCount.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Anos encontrados</dt>
          <dd>{yearList(summary.foundYears)}</dd>
        </div>
        <div>
          <dt>Empenhado nessas linhas</dt>
          <dd>{formatBrlDecimal(summary.committedAmount)}</dd>
        </div>
        <div>
          <dt>Pago efetivo nessas linhas</dt>
          <dd>{formatBrlDecimal(summary.effectivePaidAmount)}</dd>
        </div>
      </dl>
      <div className="transfer-author-audit-notes">
        {summary.observedWithoutAuthorYears.length > 0 ? (
          <p>
            <strong>Há dados da cidade, mas não deste autor:</strong>{" "}
            em {yearList(summary.observedWithoutAuthorYears)}, a fonte contém
            registro(s) territorializado(s) em Barreiras, porém nenhum
            atribuído a {summary.authorName}.
          </p>
        ) : null}
        {summary.emptyMunicipalYears.length > 0 ? (
          <p>
            <strong>A fonte não trouxe linhas para Barreiras:</strong>{" "}
            {yearList(summary.emptyMunicipalYears)}. Isso descreve o arquivo
            oficial consultado e não significa valor financeiro zero.
          </p>
        ) : null}
        {summary.unresolvedYears.length > 0 ? (
          <p>
            <strong>Cobertura ainda inconclusiva:</strong>{" "}
            {yearList(summary.unresolvedYears)}. Esses anos não entram em
            conclusões até a coleta ser estabilizada.
          </p>
        ) : null}
      </div>
      <p className="transfer-author-audit-caveat">
        “Não encontrado nesta série” não significa que o parlamentar não tenha
        apresentado emendas ou trabalhado por Barreiras. Significa apenas que
        não localizamos, nesta base específica, outra linha de execução federal
        territorializada no município e atribuída a ele.
      </p>
    </aside>
  );
}

function ReconciledRankingPanel({
  people,
  collectives,
  summary,
}: Readonly<{
  people: readonly ReconciledParliamentaryTransferRanking[] | null;
  collectives: readonly ReconciledParliamentaryTransferRanking[] | null;
  summary: ParliamentaryTransferReconciliationSummary | null;
}>) {
  if (people === null || collectives === null || summary === null) {
    return (
      <section className="transfer-ranking" aria-labelledby="reconciled-ranking-title">
        <div className="transfer-section-heading">
          <div>
            <span className="eyebrow">Visão consolidada</span>
            <h2 id="reconciled-ranking-title">Conferência entre as bases em atualização</h2>
          </div>
        </div>
        <p className="transfer-empty">
          As séries oficiais continuam disponíveis abaixo. A consolidação que impede
          contagem duplicada será exibida assim que a atualização do banco terminar.
        </p>
      </section>
    );
  }
  return (
    <section className="transfer-ranking" aria-labelledby="reconciled-ranking-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Ranking consolidado e auditável</span>
          <h2 id="reconciled-ranking-title">Quem aparece nas duas bases sem duplicar valores</h2>
        </div>
        <p>{formatBrlDecimal(summary.publishedDestinationAmount)} identificados nas fontes</p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Como conferimos</strong>
        <p>
          {summary.exactMatchCount === 0
            ? "Cruzamos proposta e número oficial da emenda. Até agora, nenhuma emenda aparece nas duas bases ao mesmo tempo — cada registro abaixo vem de uma única fonte e conta uma única vez."
            : `Cruzamos proposta e número oficial da emenda. As ${summary.exactMatchCount.toLocaleString("pt-BR")} correspondência(s) exata(s) contam uma única vez.`}
          {summary.conflictCount > 0
            ? ` ${summary.conflictCount.toLocaleString("pt-BR")} conflito(s) entre as bases ficam visíveis para auditoria, mas fora dos totais.`
            : ""}
        </p>
        <p>
          Há {summary.currentOnlyCount.toLocaleString("pt-BR")} registro(s) apenas na API atual e {" "}
          {summary.historicalOnlyCount.toLocaleString("pt-BR")} apenas no arquivo histórico. Isso indica cobertura diferente,
          não erro nem irregularidade.
        </p>
        <p>
          Estas duas bases cobrem <strong>convênios e transferências</strong>.
          Emendas executadas diretamente no orçamento de órgãos federais não
          passam por aqui:{" "}
          <a href="/recursos?origem=federal-execucao">
            veja a aba Federal · execução direta (CGU) →
          </a>
        </p>
      </aside>
      <h3>Autoria individual</h3>
      <ReconciledRankingTable
        rows={people}
        emptyCopy="Nenhuma autoria individual consolidada foi encontrada."
      />
      <h3>Comissões e bancadas</h3>
      <ReconciledRankingTable
        rows={collectives}
        emptyCopy="Nenhuma autoria coletiva consolidada foi encontrada."
      />
    </section>
  );
}

function HistoricalRankingTable({
  rows,
  emptyCopy,
}: Readonly<{
  rows: readonly HistoricalParliamentaryAmendmentRanking[];
  emptyCopy: string;
}>) {
  if (rows.length === 0) return <p className="transfer-empty">{emptyCopy}</p>;
  return (
    <div className="transfer-ranking-list">
      {rows.map((row) => (
        <article
          className="transfer-ranking-card"
          key={`historical:${row.authorKind}:${row.authorKey}`}
        >
          <span className="transfer-rank" aria-label={`posição ${row.rankPosition}`}>
            {row.rankPosition}
          </span>
          <div className="transfer-ranking-name">
            <h3>{row.authorName}</h3>
            <span>{authorKindLabel(row.authorKind)}</span>
          </div>
          <dl>
            <div>
              <dt>Destinado a Barreiras</dt>
              <dd>{formatBrlDecimal(row.destinationAmount)}</dd>
            </div>
            <div>
              <dt>Emendas distintas</dt>
              <dd>{row.amendmentCount.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Propostas alcançadas</dt>
              <dd>{row.proposalCount.toLocaleString("pt-BR")}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function HistoricalAmendmentCard({
  amendment,
}: Readonly<{ amendment: HistoricalParliamentaryAmendment }>) {
  return (
    <article className="transfer-card historical-amendment-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">{authorKindLabel(amendment.authorKind)}</span>
          <h3>{amendment.authorName}</h3>
          <p>
            Emenda {amendment.amendmentNumber ?? "sem número na fonte"} · {amendment.fiscalYear}
          </p>
        </div>
        <span className="transfer-status">
          {amendment.proposalStatus ?? "situação da proposta não informada"}
        </span>
      </div>

      <p className="transfer-object">
        {amendment.objectDescription ?? "Objeto não informado no arquivo consultado."}
      </p>
      <p className="transfer-beneficiary">
        <strong>Quem recebe:</strong>{" "}
        {amendment.beneficiaryName ?? "beneficiário não informado"}
      </p>

      <dl className="transfer-stage-grid">
        <div>
          <dt>Valor destinado à proposta</dt>
          <dd>{formatBrlDecimal(amendment.destinationAmount)}</dd>
          <span>Parcela da emenda associada a esta proposta de Barreiras.</span>
        </div>
        <div>
          <dt>É impositiva?</dt>
          <dd>
            {amendment.isMandatory === null
              ? "não informado"
              : amendment.isMandatory ? "sim" : "não"}
          </dd>
          <span>Classificação publicada no arquivo oficial de emendas.</span>
        </div>
        <div>
          <dt>Pagamento</dt>
          <dd>não verificado nesta série histórica</dd>
          <span>Valor destinado não comprova empenho, pagamento nem execução.</span>
        </div>
      </dl>

      <details className="transfer-details">
        <summary>Ver proposta e comprovação</summary>
        <dl>
          <div>
            <dt>Proposta</dt>
            <dd>{amendment.proposalNumber ?? amendment.proposalId}</dd>
          </div>
          <div>
            <dt>Programa da emenda</dt>
            <dd>{amendment.programCode ?? "não informado"}</dd>
          </div>
          <div>
            <dt>Hash da evidência preservada</dt>
            <dd className="transfer-hash">{amendment.artifactSha256}</dd>
          </div>
        </dl>
        <a href={amendment.sourceUrl} target="_blank" rel="noreferrer">
          Abrir arquivo oficial no Transferegov ↗
        </a>
        <p className="transfer-source-warning">
          O link abre o ZIP nacional usado na coleta e pode ser um arquivo grande.
        </p>
      </details>
    </article>
  );
}

function HistoricalAmendmentsPanel({
  amendments,
  people,
  collectives,
  scopeSummary,
}: Readonly<{
  amendments: readonly HistoricalParliamentaryAmendment[] | null;
  people: readonly HistoricalParliamentaryAmendmentRanking[] | null;
  collectives: readonly HistoricalParliamentaryAmendmentRanking[] | null;
  scopeSummary: FederalTransferScopeSummary | null;
}>) {
  return (
    <section className="transfer-catalog" aria-labelledby="historical-amendments-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Arquivo oficial desde 2021</span>
          <h2 id="historical-amendments-title">
            Emendas identificadas no acervo histórico
          </h2>
        </div>
        <p>
          {amendments === null
            ? "consulta temporariamente indisponível"
            : `${amendments.length.toLocaleString("pt-BR")} vínculo(s) comprovado(s)`}
        </p>
      </div>

      <aside className="transfer-reading-guide">
        <strong>O que estes valores significam</strong>
        <p>
          O arquivo histórico informa autor e parcela destinada à proposta de
          Barreiras. Ele não comprova empenho, pagamento nem execução. Esta série
          permanece separada da API atual para impedir dupla contagem.
        </p>
      </aside>

      {scopeSummary && scopeSummary.excludedRegionalProposalCount > 0 ? (
        <aside className="transfer-reading-guide" aria-label="Registros regionais excluídos">
          <strong>
            {scopeSummary.excludedRegionalAmendmentCount.toLocaleString("pt-BR")} registro(s)
            regional(is) não atribuídos a Barreiras
          </strong>
          <p>
            A fonte associa {scopeSummary.excludedRegionalProposalCount.toLocaleString("pt-BR")} proposta(s)
            a um consórcio regional, mas não comprova que o objeto foi executado em
            Barreiras. Por isso, {formatBrlDecimal(
              scopeSummary.excludedRegionalDestinationAmount,
            )} permanecem preservados para auditoria, mas não entram neste ranking.
          </p>
        </aside>
      ) : null}

      {people !== null ? (
        <section className="transfer-ranking" aria-labelledby="historical-people-title">
          <div className="transfer-section-heading">
            <div>
              <span className="eyebrow">Somente pessoas</span>
              <h3 id="historical-people-title">Ranking histórico de autoria individual</h3>
            </div>
            <p>Ordenado pelo valor destinado às propostas de Barreiras.</p>
          </div>
          <HistoricalRankingTable
            rows={people}
            emptyCopy="Nenhuma autoria individual foi identificada no acervo histórico."
          />
        </section>
      ) : null}

      {collectives !== null ? (
        <section className="transfer-ranking" aria-labelledby="historical-collective-title">
          <div className="transfer-section-heading">
            <div>
              <span className="eyebrow">Comissões e bancadas</span>
              <h3 id="historical-collective-title">Autoria coletiva no acervo histórico</h3>
            </div>
            <p>Estes valores não são atribuídos a qualquer parlamentar individual.</p>
          </div>
          <HistoricalRankingTable
            rows={collectives}
            emptyCopy="Nenhuma autoria coletiva foi identificada no acervo histórico."
          />
        </section>
      ) : null}

      {amendments === null ? (
        <p className="transfer-empty">
          A consulta histórica não respondeu. Isso não significa ausência de emendas.
        </p>
      ) : amendments.length === 0 ? (
        <p className="transfer-empty">Nenhuma emenda histórica foi encontrada no recorte.</p>
      ) : (
        <details className="historical-proposal-year">
          <summary>
            <span>Ver emenda por emenda</span>
            <small>{amendments.length.toLocaleString("pt-BR")} registro(s)</small>
          </summary>
          <div className="transfer-card-list">
            {amendments.map((amendment) => (
              <HistoricalAmendmentCard
                amendment={amendment}
                key={amendment.externalTransferKey}
              />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function TransferCard({ transfer }: Readonly<{ transfer: ParliamentaryTransfer }>) {
  const exact = transfer.stageAttributionStatus === "exact_single_distribution";
  return (
    <article className="transfer-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">{authorKindLabel(transfer.authorKind)}</span>
          <h3>{transfer.authorName}</h3>
          <p>
            Emenda {transfer.amendmentNumber ?? "sem número na fonte"} · {transfer.fiscalYear}
          </p>
        </div>
        <span className="transfer-status">{transfer.proposalStatus ?? "situação não informada"}</span>
      </div>

      <p className="transfer-object">
        {transfer.objectDescription ?? "Objeto não informado pela fonte consultada."}
      </p>
      <p className="transfer-beneficiary">
        <strong>Quem recebe:</strong>{" "}
        {transfer.beneficiaryName ?? "beneficiário não informado"}
      </p>

      <dl className="transfer-stage-grid">
        <div>
          <dt>Valor destinado</dt>
          <dd>{formatBrlDecimal(transfer.destinationAmount)}</dd>
          <span>Valor atribuído a esta emenda na distribuição oficial.</span>
        </div>
        <div>
          <dt>Valor empenhado</dt>
          <dd>
            {exact && transfer.committedAmount !== null
              ? formatBrlDecimal(transfer.committedAmount)
              : unavailableAmount("commitment")}
          </dd>
          <span>Empenho é promessa orçamentária; ainda não significa pagamento.</span>
        </div>
        <div>
          <dt>Valor pago confirmado</dt>
          <dd>
            {exact && transfer.paidAmount !== null
              ? formatBrlDecimal(transfer.paidAmount)
              : unavailableAmount("payment")}
          </dd>
          <span>Somente ordens de pagamento marcadas como pagas na fonte oficial.</span>
        </div>
      </dl>

      {!exact ? (
        <p className="transfer-caution">
          Esta proposta possui mais de uma distribuição de recurso. Os estágios
          financeiros não foram atribuídos a um autor para evitar crédito indevido.
        </p>
      ) : null}

      <details className="transfer-details">
        <summary>Ver comprovação e detalhes</summary>
        <dl>
          <div>
            <dt>Ordem bancária</dt>
            <dd>{transfer.bankOrderNumber ?? "não encontrada na fonte consultada"}</dd>
          </div>
          <div>
            <dt>Data da ordem bancária</dt>
            <dd>{formatDate(transfer.bankOrderDate)}</dd>
          </div>
          <div>
            <dt>Proposta no Transferegov</dt>
            <dd>{transfer.proposalId}</dd>
          </div>
          <div>
            <dt>Hash da evidência preservada</dt>
            <dd className="transfer-hash">{transfer.artifactSha256}</dd>
          </div>
        </dl>
        <a href={transfer.sourceUrl} target="_blank" rel="noreferrer">
          Abrir registro oficial no Transferegov ↗
        </a>
      </details>
    </article>
  );
}

function HistoricalProposalCard({
  proposal,
}: Readonly<{ proposal: FederalTransferProposal }>) {
  return (
    <article className="transfer-card historical-proposal-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">Proposta federal cadastrada</span>
          <h3>
            Proposta {proposal.proposalNumber ?? proposal.proposalId}
          </h3>
          <p>
            {proposal.modality ?? "modalidade não informada"} · {proposal.fiscalYear}
            {proposal.proposalDateText ? ` · cadastrada em ${proposal.proposalDateText}` : ""}
          </p>
        </div>
        <span className="transfer-status">
          {proposal.proposalStatus ?? "situação não informada"}
        </span>
      </div>

      <p className="transfer-object">
        {proposal.objectDescription ?? "Objeto não informado no arquivo consultado."}
      </p>
      <p className="transfer-beneficiary">
        <strong>Proponente:</strong>{" "}
        {proposal.proponentName ?? "não informado"}
        {proposal.federalBodyName ? ` · órgão federal: ${proposal.federalBodyName}` : ""}
      </p>

      <dl className="transfer-stage-grid">
        <div>
          <dt>Valor global proposto</dt>
          <dd>
            {proposal.globalAmount === null
              ? "não informado"
              : formatBrlDecimal(proposal.globalAmount)}
          </dd>
          <span>Valor previsto na proposta; não comprova transferência.</span>
        </div>
        <div>
          <dt>Repasse solicitado</dt>
          <dd>
            {proposal.requestedTransferAmount === null
              ? "não informado"
              : formatBrlDecimal(proposal.requestedTransferAmount)}
          </dd>
          <span>Pedido registrado, ainda diferente de dinheiro empenhado ou pago.</span>
        </div>
        <div>
          <dt>Contrapartida proposta</dt>
          <dd>
            {proposal.counterpartAmount === null
              ? "não informada"
              : formatBrlDecimal(proposal.counterpartAmount)}
          </dd>
          <span>Parte prevista para o proponente no cadastro original.</span>
        </div>
      </dl>

      <p className="transfer-caution">
        <strong>Autoria parlamentar não disponível nesta fonte.</strong>{" "}
        Esta ficha de proposta, isoladamente, não entra no ranking. Quando o
        arquivo oficial de emendas comprova autor e valor destinado, a ligação
        aparece no painel histórico acima; pagamento continua dependendo de
        evidência financeira própria.
      </p>

      <details className="transfer-details">
        <summary>Ver situação, órgão e evidência</summary>
        <dl>
          <div>
            <dt>Situação do projeto básico</dt>
            <dd>{proposal.basicProjectStatus ?? "não informada"}</dd>
          </div>
          <div>
            <dt>Área do investimento</dt>
            <dd>{proposal.investmentItem ?? "não informada"}</dd>
          </div>
          <div>
            <dt>Órgão federal superior</dt>
            <dd>{proposal.superiorFederalBodyName ?? "não informado"}</dd>
          </div>
          <div>
            <dt>Hash da evidência preservada</dt>
            <dd className="transfer-hash">{proposal.artifactSha256}</dd>
          </div>
        </dl>
        <a href={proposal.sourceUrl} target="_blank" rel="noreferrer">
          Arquivo oficial completo no Transferegov ↗
        </a>
        <p className="transfer-source-warning">
          O link abre o ZIP nacional usado na coleta e pode ser um arquivo grande.
        </p>
      </details>
    </article>
  );
}

function HistoricalProposalsPanel({
  proposals,
}: Readonly<{ proposals: readonly FederalTransferProposal[] | null }>) {
  if (proposals === null) {
    return (
      <section className="transfer-catalog" aria-labelledby="historical-proposals-title">
        <div className="transfer-section-heading">
          <div>
            <span className="eyebrow">Acervo histórico federal</span>
            <h2 id="historical-proposals-title">Propostas federais encontradas desde 2021</h2>
          </div>
        </div>
        <p className="transfer-empty">
          O catálogo histórico está temporariamente indisponível. Isso não significa
          que não existam propostas.
        </p>
      </section>
    );
  }

  const proposalsByYear = new Map<number, FederalTransferProposal[]>();
  for (const proposal of proposals) {
    const yearRows = proposalsByYear.get(proposal.fiscalYear) ?? [];
    yearRows.push(proposal);
    proposalsByYear.set(proposal.fiscalYear, yearRows);
  }
  const yearGroups = [...proposalsByYear.entries()].sort(
    ([leftYear], [rightYear]) => rightYear - leftYear,
  );

  return (
    <section className="transfer-catalog" aria-labelledby="historical-proposals-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Acervo histórico federal</span>
          <h2 id="historical-proposals-title">Propostas federais encontradas desde 2021</h2>
        </div>
        <p>{proposals.length.toLocaleString("pt-BR")} registro(s) preservado(s)</p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Como interpretar</strong>
        <p>
          Uma proposta não significa dinheiro pago nem obra executada. Ela registra
          uma intenção formal apresentada ao Governo Federal. Situação, valores e
          objeto abaixo são os campos do arquivo oficial; autoria e pagamento só
          aparecem no ranking quando outra fonte oficial comprova essas etapas.
        </p>
      </aside>
      {yearGroups.length === 0 ? (
        <p className="transfer-empty">Nenhuma proposta histórica foi encontrada no recorte.</p>
      ) : (
        <div className="historical-proposal-years">
          {yearGroups.map(([year, rows], index) => (
            <details className="historical-proposal-year" key={year} open={index === 0}>
              <summary>
                <span>{year}</span>
                <small>{rows.length.toLocaleString("pt-BR")} proposta(s)</small>
              </summary>
              <div className="transfer-card-list">
                {rows.map((proposal) => (
                  <HistoricalProposalCard proposal={proposal} key={proposal.proposalId} />
                ))}
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

type ParliamentaryResourcesPageProps = Readonly<{
  searchParams: Promise<{
    ano?: string | string[];
    autor?: string | string[];
    documento_ano?: string | string[];
    documento_autor?: string | string[];
    documento_etapa?: string | string[];
    documento_pagina?: string | string[];
    documento_q?: string | string[];
    estadual_pagina?: string | string[];
    estadual_autor?: string | string[];
    estadual_situacao?: string | string[];
    estadual_q?: string | string[];
    origem?: string | string[];
  }>;
}>;

export default async function ParliamentaryResourcesPage({
  searchParams,
}: ParliamentaryResourcesPageProps) {
  const params = await searchParams;
  const sourceSelection = resolveTransferSourceSelection(params.origem);
  const parliamentaryTransferQueryScope = sourceSelection.showCurrentFederal
    ? "current" as const
    : sourceSelection.showHistoricalFederal
    ? "historical" as const
    : sourceSelection.showState
    ? "state" as const
    : "none" as const;
  const cguDocumentFilters = resolveCguDocumentFilters(params);
  const latestStateFiscalYear = Number(
    new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      timeZone: "America/Bahia",
    }).format(new Date()),
  );
  const availableStateFiscalYears = stateLoaYears(latestStateFiscalYear);
  const selectedStateFiscalYear = resolveStateLoaYear(
    sourceSelection.showState ? params.ano : undefined,
    latestStateFiscalYear,
  ) ?? latestStateFiscalYear;
  const stateLoaFilters = resolveStateLoaStudyFilters({
    estadual_pagina: sourceSelection.showState ? params.estadual_pagina : undefined,
    estadual_autor: sourceSelection.showState ? params.estadual_autor : undefined,
    estadual_situacao: sourceSelection.showState ? params.estadual_situacao : undefined,
    estadual_q: sourceSelection.showState ? params.estadual_q : undefined,
  });
  const [
    result,
    legislatureRankingsResult,
    legislatureCoverageResult,
    legislatureYearCoverageResult,
    cguFederalAmendmentsResult,
    cguFederalAmendmentDocumentsResult,
    cguLegislatureRankingsResult,
    federalSourceCoverageResult,
    stateSourceCoverageResult,
    bahiaSpecialTransfersResult,
    bahiaStateExecutionCoverageResult,
  ] = await Promise.all([
    getPublicParliamentaryTransfers({
      stateFiscalYear: selectedStateFiscalYear,
      stateLoaFilters,
      queryScope: parliamentaryTransferQueryScope,
    }),
    sourceSelection.showLegislatures
      ? getPublicParliamentaryLegislatureRankings()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showLegislatures
      ? getPublicParliamentaryLegislatureCoverage()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showLegislatures
      ? getPublicParliamentaryLegislatureYearCoverage()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showCguExecution
      ? getPublicCguFederalAmendments()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showCguExecution
      ? getPublicCguFederalAmendmentDocuments(cguDocumentFilters)
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showLegislatures
      ? getPublicCguFederalAmendmentLegislatureRankings()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showState
      ? Promise.resolve({ state: "unavailable" as const })
      : getPublicFederalTransferSourceCoverage(),
    sourceSelection.showState
      ? getPublicStateAmendmentSourceCoverage()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showState
      ? getPublicBahiaSpecialTransfers()
      : Promise.resolve({ state: "unavailable" as const }),
    sourceSelection.showState
      ? getPublicBahiaStateExecutionCoverage()
      : Promise.resolve({ state: "unavailable" as const }),
  ]);
  const federalSourceCoverage = federalSourceCoverageResult.state === "available"
    ? federalSourceCoverageResult.rows
    : null;
  const stateSourceCoverage = stateSourceCoverageResult.state === "available"
    ? stateSourceCoverageResult.rows
    : null;
  const bahiaStateExecutionCoverage =
    bahiaStateExecutionCoverageResult.state === "available"
      ? bahiaStateExecutionCoverageResult.rows
      : null;
  const legislatureRankingGroups =
    legislatureRankingsResult.state === "available"
      ? legislatureRankingsResult.groups
      : null;
  const legislatureCoverage =
    legislatureCoverageResult.state === "available"
      ? legislatureCoverageResult.rows
      : null;
  const legislatureYearCoverage =
    legislatureYearCoverageResult.state === "available"
      ? legislatureYearCoverageResult.rows
      : null;
  const selectedFiscalYear = result.state === "available" &&
      sourceSelection.showCurrentFederal
    ? resolveCurrentFederalTransferYear(params.ano, result.coverage)
    : null;
  const [currentTransferResult, currentRankings] = selectedFiscalYear === null
    ? [
        { state: "unavailable" as const },
        { state: "unavailable" as const },
      ]
    : await Promise.all([
        getPublicCurrentParliamentaryTransfers(selectedFiscalYear),
        getPublicParliamentaryTransferRankings(selectedFiscalYear),
      ]);
  const currentTransfers = currentTransferResult.state === "available"
    ? currentTransferResult.transfers
    : [];
  const availableFiscalYears = result.state === "available" && result.coverage !== null
    ? [...new Set(result.coverage.map((row) => row.fiscalYear))]
      .sort((left, right) => right - left)
    : [];

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/financas">Finanças</a>
            <a href="/representantes">Quem decide</a>
            <a href="/licitacoes">Compras</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="resources-title">
        <div className="section-heading">
          <span className="eyebrow">Dinheiro que chega a Barreiras</span>
          <h1 id="resources-title">Quem destinou recursos para a cidade?</h1>
          <p>
            Veja o autor informado pela fonte oficial, quanto foi destinado e
            quanto chegou ao estágio de pagamento. Pessoas, comissões e bancadas
            aparecem separadas para não atribuir a um político um recurso coletivo.
          </p>
        </div>

        <aside className="transfer-reading-guide" aria-label="Como ler este painel">
          <strong>O que este ranking mede</strong>
          <p>
            Ele ordena valores oficiais de emendas encontradas para Barreiras.
            Não é uma nota geral de desempenho: não mede leis, fiscalização,
            presença, qualidade do gasto nem a execução final do objeto.
          </p>
          <p>
            “Destinado”, “empenhado” e “pago” são etapas diferentes. Campo sem
            valor significa que o dado não foi encontrado nos endpoints oficiais
            consultados — nunca que o valor é zero.
          </p>
          <ShareLink
            path={`/recursos?origem=${sourceSelection.source}`}
            message="Veja quem destinou recursos para Barreiras, com o documento oficial em cada registro:"
          />
        </aside>

        <details className="transfer-methodology" open={false}>
          <summary>Por que um parlamentar aparece em uma aba e não em outra?</summary>
          <p>
            Cada aba mostra <strong>uma fonte oficial diferente</strong>, e cada
            fonte enxerga um caminho diferente do dinheiro. O Transferegov
            registra convênios e transferências pactuados com quem recebe. O
            arquivo da CGU registra a execução do orçamento federal
            regionalizada em Barreiras — inclusive emendas aplicadas
            diretamente por órgãos federais, que nunca passam por convênio. A
            LOA da Bahia registra o que deputados estaduais autorizaram no
            orçamento do estado.
          </p>
          <p>
            Por isso, um mesmo parlamentar pode aparecer em uma fonte e não em
            outra — por exemplo, quem executou emendas direto em órgãos
            federais aparece na aba Execução federal e pode não ter nenhum
            convênio no arquivo histórico. Isso é diferença de cobertura entre
            fontes oficiais, não erro e não omissão do portal.
          </p>
          <p>
            Para impedir dupla contagem, valores de fontes diferentes{" "}
            <strong>nunca são somados</strong>. Quando uma mesma emenda aparece
            em duas fontes, ela é apenas rotulada pelo código oficial.
          </p>
        </details>

        <nav className="transfer-source-selector" aria-label="Escolher origem dos recursos">
          <a
            href="/recursos?origem=legislaturas#emendas-por-legislatura"
            aria-current={sourceSelection.source === "legislaturas" ? "page" : undefined}
          >
            <strong>Comparar por legislatura</strong>
            <span>Deputados federais e estaduais lado a lado, mandato por mandato, com todas as fontes visíveis.</span>
          </a>
          <a
            href="/recursos?origem=federal-atual"
            aria-current={sourceSelection.source === "federal-atual" ? "page" : undefined}
          >
            <strong>Federal · convênios atuais</strong>
            <span>Emendas recentes com destino e pagamento consultados na API do Transferegov.</span>
          </a>
          <a
            href="/recursos?origem=federal-historico"
            aria-current={sourceSelection.source === "federal-historico" ? "page" : undefined}
          >
            <strong>Federal · arquivo de convênios</strong>
            <span>Acervo histórico do Transferegov e conferência entre as duas séries de convênios.</span>
          </a>
          <a
            href="/recursos?origem=federal-execucao"
            aria-current={sourceSelection.source === "federal-execucao" ? "page" : undefined}
          >
            <strong>Federal · execução direta (CGU)</strong>
            <span>Orçamento federal executado em Barreiras, inclusive fora de convênios.</span>
          </a>
          <a
            href="/recursos?origem=estadual"
            aria-current={sourceSelection.source === "estadual" ? "page" : undefined}
          >
            <strong>Estadual · Bahia</strong>
            <span>LOA autorizada e pagamentos estaduais cujo objeto oficial menciona Barreiras.</span>
          </a>
        </nav>

        {!sourceSelection.showState ? (
          <FederalTransferSourceCoveragePanel rows={federalSourceCoverage} />
        ) : null}

        {sourceSelection.showLegislatures ? (
          <LegislatureTransferRankings
            coverage={legislatureCoverage}
            groups={legislatureRankingGroups}
            yearCoverage={legislatureYearCoverage}
            cguGroups={cguLegislatureRankingsResult.state === "available"
              ? cguLegislatureRankingsResult.groups
              : null}
          />
        ) : sourceSelection.showCguExecution ? (
          <CguFederalExecutionPanel
            coverage={federalSourceCoverage ?? []}
            documentFilters={cguDocumentFilters}
            documentResult={cguFederalAmendmentDocumentsResult}
            requestedAuthor={params.autor}
            requestedYear={params.ano}
            result={cguFederalAmendmentsResult}
          />
        ) : sourceSelection.showState ? (
          <>
            <BahiaSpecialTransfersPanel
              coverage={bahiaSpecialTransfersResult.state === "available"
                ? bahiaSpecialTransfersResult.coverage
                : null}
              payments={bahiaSpecialTransfersResult.state === "available"
                ? bahiaSpecialTransfersResult.payments
                : null}
              ranking={bahiaSpecialTransfersResult.state === "available"
                ? bahiaSpecialTransfersResult.ranking
                : null}
            />
            {result.state === "available" ? (
              <StateLoaPanel
                amendments={result.stateLoaAmendments}
                ranking={result.stateLoaRanking}
                execution={result.stateLoaExecution}
                executionSummary={result.stateLoaExecutionSummary}
                executionGroups={result.stateLoaExecutionGroups}
                totalCount={result.stateLoaTotalCount}
                catalogCount={result.stateLoaCatalogCount}
                availableAuthors={result.stateLoaAvailableAuthors}
                filters={result.stateLoaFilters}
                page={result.stateLoaPage}
                pageSize={result.stateLoaPageSize}
                selectedFiscalYear={selectedStateFiscalYear}
                availableFiscalYears={availableStateFiscalYears}
                coverage={stateSourceCoverage}
                executionArchiveCoverage={bahiaStateExecutionCoverage}
              />
            ) : (
              <div className="collection-unavailable" role="status">
                <div>
                  <strong>Consulta da LOA temporariamente indisponível</strong>
                  <p>Isso é uma falha de consulta, não ausência de emendas.</p>
                </div>
              </div>
            )}
          </>
        ) : result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Consulta temporariamente indisponível</strong>
              <p>Isso é uma falha de consulta, não ausência de emendas.</p>
            </div>
          </div>
        ) : (
          <>
            {sourceSelection.showCurrentFederal ? (
              <>
                {selectedFiscalYear !== null && availableFiscalYears.length > 0 ? (
                  <form
                    className="transfer-year-filter"
                    method="get"
                    aria-label="Filtrar emendas federais atuais por ano"
                  >
                    <input type="hidden" name="origem" value="federal-atual" />
                    <div>
                      <label htmlFor="transfer-year">Ano da API federal atual</label>
                      <select id="transfer-year" name="ano" defaultValue={selectedFiscalYear}>
                        {availableFiscalYears.map((year) => (
                          <option value={year} key={year}>{year}</option>
                        ))}
                      </select>
                    </div>
                    <button type="submit">Ver este ano</button>
                    <p>
                      O filtro altera a resposta rápida, as emendas e o ranking da
                      API federal atual. As outras origens permanecem nas abas acima.
                    </p>
                  </form>
                ) : null}

                <CurrentFederalTransferPanel
                  transfers={currentTransfers}
                  fiscalYear={selectedFiscalYear}
                  sourceAvailable={currentTransferResult.state === "available"}
                  coverage={result.coverage?.find((row) => row.fiscalYear === selectedFiscalYear) ?? null}
                />

                {selectedFiscalYear !== null ? (
                  <CurrentFederalRankingPanel
                    fiscalYear={selectedFiscalYear}
                    result={currentRankings}
                  />
                ) : null}

                <CoveragePanel rows={result.coverage} />
              </>
            ) : null}

            {sourceSelection.showHistoricalFederal ? (
              <>
                <ReconciledRankingPanel
                  people={result.reconciledPeople}
                  collectives={result.reconciledCollectives}
                  summary={result.reconciliationSummary}
                />

                <HistoricalAmendmentsPanel
                  amendments={result.historicalAmendments}
                  people={result.historicalPeople}
                  collectives={result.historicalCollectives}
                  scopeSummary={result.scopeSummary}
                />

                <HistoricalProposalsPanel proposals={result.historicalProposals} />
              </>
            ) : null}

          </>
        )}

        <details className="transfer-methodology">
          <summary>Metodologia e limites do ranking</summary>
          <p>
            A projeção usa o registro mais recente de cada item bruto preservado,
            sem duplicar reexecuções do coletor. Os totais são calculados em SQL
            com valores decimais exatos. Pagamento só é contado quando a ordem de
            pagamento oficial está marcada como paga. Se uma proposta tiver mais
            de uma distribuição, seus estágios não são creditados a qualquer autor.
          </p>
          <p>
            Fonte inicial: API publica Gestao de Parcerias do Transferegov,
            filtrada pelo código IBGE 2903201. O acervo será ampliado com outras
            bases oficiais federais e estaduais, sempre mantendo fonte e evidência.
          </p>
        </details>
      </section>
    </main>
  );
}
