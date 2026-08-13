import type { Metadata } from "next";

import {
  getPublicParliamentaryTransfers,
  parliamentaryTransferAuthorAnchor,
  type FederalTransferProposal,
  type HistoricalParliamentaryAmendment,
  type HistoricalParliamentaryAmendmentRanking,
  type ParliamentaryTransfer,
  type ParliamentaryTransferCoverage,
  type ParliamentaryTransferRanking,
} from "../../lib/parliamentary-transfers";
import { formatBrlDecimal } from "../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Recursos destinados a Barreiras",
  description:
    "Propostas federais e emendas destinadas a Barreiras, com autoria e estágios financeiros separados por fonte oficial.",
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

function CoveragePanel({
  rows,
}: Readonly<{ rows: readonly ParliamentaryTransferCoverage[] | null }>) {
  return (
    <section className="transfer-coverage" aria-labelledby="transfer-coverage-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Cobertura da API atual</span>
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
        Nenhuma proposta encontrada na API atual não prova ausência em outras bases
        oficiais. Por isso, o arquivo histórico federal aparece em uma seção
        separada abaixo, sem transformar dado não coletado em zero.
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
}: Readonly<{
  amendments: readonly HistoricalParliamentaryAmendment[] | null;
  people: readonly HistoricalParliamentaryAmendmentRanking[] | null;
  collectives: readonly HistoricalParliamentaryAmendmentRanking[] | null;
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
            <HistoricalAmendmentsPanel
              amendments={result.historicalAmendments}
              people={result.historicalPeople}
              collectives={result.historicalCollectives}
            />

            <HistoricalProposalsPanel proposals={result.historicalProposals} />

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
