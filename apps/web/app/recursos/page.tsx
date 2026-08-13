import type { Metadata } from "next";

import {
  getPublicParliamentaryTransfers,
  parliamentaryTransferAuthorAnchor,
  type ParliamentaryTransfer,
  type ParliamentaryTransferCoverage,
  type ParliamentaryTransferRanking,
} from "../../lib/parliamentary-transfers";
import { formatBrlDecimal } from "../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Recursos destinados a Barreiras",
  description:
    "Emendas destinadas a Barreiras, autoria e estágios financeiros comprovados em fonte oficial.",
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
    return `Fonte consultada: ${row.proposalCount.toLocaleString("pt-BR")} proposta(s); ${row.publishedAmendmentCount.toLocaleString("pt-BR")} emenda(s) publicada(s).`;
  }
  if (row.coverageStatus === "empty") {
    return "Fonte consultada: nenhuma proposta encontrada nesta API para o ano.";
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

function CoveragePanel({
  rows,
}: Readonly<{ rows: readonly ParliamentaryTransferCoverage[] | null }>) {
  return (
    <section className="transfer-coverage" aria-labelledby="transfer-coverage-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Cobertura da fonte</span>
          <h2 id="transfer-coverage-title">Quais anos já conferimos?</h2>
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
        Nenhuma proposta encontrada nesta API não prova ausência em outras bases
        oficiais. O Barreiras 360 ampliará o cruzamento sem transformar dado não
        coletado em zero.
      </p>
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

export default async function ParliamentaryResourcesPage() {
  const result = await getPublicParliamentaryTransfers();

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
        </aside>

        {result.state === "available" ? <CoveragePanel rows={result.coverage} /> : null}

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Consulta temporariamente indisponível</strong>
              <p>Isso é uma falha de consulta, não ausência de emendas.</p>
            </div>
          </div>
        ) : (
          <>
            <section className="transfer-ranking" aria-labelledby="people-ranking-title">
              <div className="transfer-section-heading">
                <div>
                  <span className="eyebrow">Autoria individual</span>
                  <h2 id="people-ranking-title">Parlamentares que destinaram recursos</h2>
                </div>
                <p>Ordenação principal: valor pago confirmado; depois, valor destinado.</p>
              </div>
              <RankingTable
                rows={result.people}
                emptyCopy="Nenhuma autoria individual foi encontrada no recorte oficial coletado."
              />
            </section>

            <section className="transfer-ranking" aria-labelledby="collective-ranking-title">
              <div className="transfer-section-heading">
                <div>
                  <span className="eyebrow">Autoria coletiva</span>
                  <h2 id="collective-ranking-title">Comissões e bancadas</h2>
                </div>
                <p>Estes valores não entram no ranking pessoal de nenhum parlamentar.</p>
              </div>
              <RankingTable
                rows={result.collectives}
                emptyCopy="Nenhuma autoria coletiva foi encontrada no recorte oficial coletado."
              />
            </section>

            <section className="transfer-catalog" aria-labelledby="transfer-catalog-title">
              <div className="transfer-section-heading">
                <div>
                  <span className="eyebrow">Emenda por emenda</span>
                  <h2 id="transfer-catalog-title">O caminho comprovado do recurso</h2>
                </div>
                <p>{result.transfers.length.toLocaleString("pt-BR")} registro(s) no recorte atual</p>
              </div>
              <div className="transfer-card-list">
                {result.transfers.map((transfer) => (
                  <TransferCard transfer={transfer} key={transfer.externalTransferKey} />
                ))}
              </div>
            </section>
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
