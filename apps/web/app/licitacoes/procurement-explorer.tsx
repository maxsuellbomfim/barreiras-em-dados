import type { Procurement } from "../../lib/pncp-procurements";
import { pncpProcurementSourceUrl } from "../../lib/pncp-source-url";

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

function formatCount(value: number) {
  return value.toLocaleString("pt-BR");
}

function formatOptionalDate(value: string | null) {
  return value ? formatDate(value) : "não informado";
}

function evidenceLabel(value: string) {
  return {
    contratacao: "Contratação",
    contrato: "Contrato",
    empenho: "Empenho",
    liquidacao: "Liquidação",
    pagamento: "Pagamento",
  }[value] ?? value;
}

export function procurementDetailPath(controlNumber: string): string {
  return `/licitacoes/contratacao/${encodeURIComponent(controlNumber)}`;
}

function executionLabel(procurement: Procurement): string {
  const summary = procurement.executionSummary;
  if (summary.state === "linked") {
    return `${formatCount(summary.contractsCount)} contrato(s), ${formatCount(summary.paymentsCount)} pagamento(s) ligados`;
  }
  if (summary.state === "no_linked_execution") return "sem vínculo de execução publicado";
  if (summary.state === "not_normalized") return "vínculos em preparação";
  return "resumo de execução indisponível";
}

export function ProcurementCard({
  procurement,
  compact = false,
}: Readonly<{ procurement: Procurement; compact?: boolean }>) {
  const sourceUrl = pncpProcurementSourceUrl(procurement.controlNumber);
  const queryState = procurement.queryStatus?.state ?? "unavailable";
  const queryLabels = {
    unknown: "Verificação individual ainda não disponível",
    pending: "Consulta pendente de conclusão",
    awaiting_source_publication: "Aguardando publicação de contrato no PNCP",
    query_complete: "Consulta de contratos concluída",
    empty_confirmed: "Resposta vazia confirmada nesta consulta",
    inconclusive: "Resposta do PNCP inconclusiva",
    partial: "Consulta com páginas pendentes",
    interrupted: "Consulta interrompida",
    unavailable: "Estado da consulta temporariamente indisponível",
  };
  return (
    <article className="digest-card" aria-label="Contratação pública">
      <div className="track-top">
        <span>
          {procurement.modalidade ?? "Contratação"} ·{" "}
          {procurement.dataPublicacao
            ? formatDate(procurement.dataPublicacao)
            : `${procurement.ano}`}
        </span>
        <span className="track-status">
          {procurement.situacao ?? "situação no PNCP"}
        </span>
      </div>
      <h2 className="procurement-object">
        {compact ? (
          <a href={procurementDetailPath(procurement.controlNumber)}>
            {procurement.objeto}
          </a>
        ) : (
          procurement.objeto
        )}
      </h2>
      <dl className="procurement-values">
        {procurement.unidade ? (
          <div>
            <dt>Unidade compradora</dt>
            <dd>{procurement.unidade}</dd>
          </div>
        ) : null}
        <div>
          <dt>Valor estimado (PNCP)</dt>
          <dd>
            {procurement.valorEstimado !== null
              ? currencyFormatter.format(procurement.valorEstimado)
              : "não informado"}
          </dd>
        </div>
        <div>
          <dt>Valor homologado (PNCP)</dt>
          <dd>
            {procurement.valorHomologado !== null
              ? currencyFormatter.format(procurement.valorHomologado)
              : "ainda sem homologação registrada"}
          </dd>
        </div>
      </dl>
      {compact ? (
        <>
          <p className="meta-note">
            {formatCount(procurement.itens.length)} item(ns) ·{" "}
            {formatCount(procurement.resultados.length)} resultado(s) homologado(s) ·{" "}
            {executionLabel(procurement)} · {queryLabels[queryState].toLowerCase()}
          </p>
          <p>
            <a href={procurementDetailPath(procurement.controlNumber)}>
              Ver itens, quem venceu, execução e evidências →
            </a>
          </p>
        </>
      ) : (
        <>
      {procurement.valorEstimado === null ? (
        <p className="procurement-privacy-note">
          O PNCP não informou um valor estimado neste registro. Isso pode ocorrer
          quando o edital mantém o orçamento sob sigilo ou quando a etapa ainda
          não foi atualizada. Acompanharemos novas versões do processo e manteremos
          o edital oficial como fonte.
        </p>
      ) : null}
      {procurement.valorHomologado === null ? (
        <p className="procurement-privacy-note">
          Ainda não há valor homologado publicado pelo PNCP. Quando a contratação
          avançar, o próximo registro coletado poderá preencher esse campo.
        </p>
      ) : null}
      {procurement.itens.length > 0 ? (
        <details className="procurement-items">
          <summary>
            Itens da contratação ({formatCount(procurement.itens.length)})
          </summary>
          <ul>
            {procurement.itens.map((item) => (
              <li key={`${procurement.controlNumber}-${item.numeroItem}`}>
                <strong>Item {item.numeroItem}</strong> · {item.descricao}
                <br />
                {item.quantidade !== null ? `Quantidade: ${item.quantidade}` : "Quantidade não informada"}
                {item.unidade ? ` ${item.unidade}` : ""}
                {item.valorUnitarioEstimado !== null
                  ? ` · unitário ${currencyFormatter.format(item.valorUnitarioEstimado)}`
                  : " · valor unitário não informado"}
                {item.valorTotal !== null
                  ? ` · total ${currencyFormatter.format(item.valorTotal)}`
                  : " · valor total não informado"}
                {item.situacao ? ` · ${item.situacao}` : ""}
                {item.contextoPreco ? (
                  <span className="procurement-price-context">
                    <br />
                    Contexto de {item.contextoPreco.observacoes} observações literalmente iguais:
                    intervalo de {currencyFormatter.format(item.contextoPreco.minimo)} a {currencyFormatter.format(item.contextoPreco.maximo)},
                    mediana {currencyFormatter.format(item.contextoPreco.mediana)}.
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="meta-note">
            Itens e valores são os informados pelo PNCP. O intervalo acima é apenas
            contexto estatístico de descrições e unidades literalmente iguais; não
            é comparação de mercado nem conclusão de irregularidade.
          </p>
        </details>
      ) : (
        <p className="meta-note">Nenhum item normalizado foi publicado para esta contratação.</p>
      )}
      {procurement.resultados.length > 0 ? (
        <details className="procurement-results">
          <summary>
            Quem venceu ({procurement.resultados.length}{" "}
            {procurement.resultados.length === 1 ? "item" : "itens"})
          </summary>
          <ul>
            {procurement.resultados.map((resultado) => (
              <li key={`${procurement.controlNumber}-${resultado.numeroItem}`}>
                <strong>{resultado.fornecedor}</strong>
                {resultado.niFornecedor
                  ? ` · CNPJ ${resultado.niFornecedor}`
                  : resultado.tipoPessoa === "PF"
                    ? " · pessoa física (documento preservado)"
                    : ""}
                {resultado.valorTotalHomologado !== null
                  ? ` — ${currencyFormatter.format(
                      resultado.valorTotalHomologado,
                    )}`
                  : ""}
                {resultado.dataResultado
                  ? ` (homologado em ${formatDate(resultado.dataResultado)})`
                  : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="meta-note">
          Nenhum resultado homologado registrado até agora para esta
          contratação.
        </p>
      )}
      <div className="procurement-query-status">
        <p><strong>{queryLabels[queryState]}</strong></p>
        <p className="meta-note">
          {queryState === "awaiting_source_publication"
            ? "Na data da consulta, o PNCP informou que não havia contrato publicado para esta compra. A resposta foi preservada. Isso não prova que o contrato não exista em outras fontes. A compra permanece na fila de reconsulta."
            : queryState === "empty_confirmed"
            ? "O PNCP devolveu uma lista vazia de contratos nesta consulta, e essa resposta foi preservada. Isso não prova ausência de contratos em outros períodos ou fontes."
            : queryState === "query_complete"
              ? "As páginas desta consulta foram verificadas e preservadas. Isso não comprova pagamentos nem execução do contrato, nem cobertura de todo o histórico."
              : queryState === "unknown"
                ? "Ainda não há evidência individual validada para informar o resultado desta consulta. Isso não significa que a contratação nunca tenha sido coletada."
                : "Ainda não foi possível confirmar o resultado completo da consulta de contratos. Os vínculos já publicados continuam disponíveis abaixo."}
        </p>
        {procurement.queryStatus?.checkedAt ? (
          <p className="meta-note">
            Consulta registrada em <time dateTime={procurement.queryStatus.checkedAt}>
              {new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Bahia" }).format(new Date(procurement.queryStatus.checkedAt))}
            </time>{" (horário de Barreiras)"}
          </p>
        ) : null}
        {procurement.queryStatus?.sourceUrl ? (
          <p className="meta-note"><a href={procurement.queryStatus.sourceUrl} target="_blank" rel="noreferrer">Conferir a contratação na fonte oficial (PNCP)</a></p>
        ) : null}
      </div>
      <p className="meta-note procurement-coverage-note">
        Este card mostra os vínculos publicados na plataforma; isso não confirma que todos os contratos e pagamentos foram coletados.
        {" "}A ausência de um vínculo aqui não prova que ele não exista na fonte oficial.
      </p>
      <details className="procurement-execution">
        <summary>Execução financeira ligada</summary>
        {procurement.executionSummary.state === "linked" ? (
          <>
            <p className="meta-note">
              Os valores abaixo se referem somente aos registros vinculados nesta plataforma.
              Os valores são líquidos de cancelamentos e reversões.
            </p>
            <dl className="procurement-values procurement-execution-values">
              <div>
                <dt>Contratos</dt>
                <dd>{formatCount(procurement.executionSummary.contractsCount)}</dd>
              </div>
              <div>
                <dt>Empenhos</dt>
                <dd>{formatCount(procurement.executionSummary.commitmentsCount)}</dd>
              </div>
              <div>
                <dt>Liquidações</dt>
                <dd>{formatCount(procurement.executionSummary.liquidationsCount)}</dd>
              </div>
              <div>
                <dt>Pagamentos</dt>
                <dd>{formatCount(procurement.executionSummary.paymentsCount)}</dd>
              </div>
              <div>
                <dt>Valor contratado</dt>
                <dd>{currencyFormatter.format(procurement.executionSummary.contractCurrentAmount)}</dd>
              </div>
              <div>
                <dt>Empenhado</dt>
                <dd>{currencyFormatter.format(procurement.executionSummary.committedAmount)}</dd>
              </div>
              <div>
                <dt>Liquidado</dt>
                <dd>{currencyFormatter.format(procurement.executionSummary.liquidatedAmount)}</dd>
              </div>
              <div>
                <dt>Pago</dt>
                <dd>{currencyFormatter.format(procurement.executionSummary.paidAmount)}</dd>
              </div>
            </dl>
            {procurement.executionSummary.contracts.length > 0 ? (
              <details className="procurement-contract-details" open>
                <summary>
                  Detalhes dos contratos ({formatCount(procurement.executionSummary.contracts.length)})
                </summary>
                <ul>
                  {procurement.executionSummary.contracts.map((contract) => (
                    <li key={contract.externalId}>
                      <strong>
                        {contract.contractNumber
                          ? `Contrato ${contract.contractNumber}`
                          : "Contrato sem número informado"}
                      </strong>
                      {contract.supplierName ? ` · ${contract.supplierName}` : ""}
                      {contract.supplierRegistrationNumber
                        ? ` · CNPJ ${contract.supplierRegistrationNumber}`
                        : ""}
                      <br />
                      Valor atual: {contract.currentAmount !== null
                        ? currencyFormatter.format(contract.currentAmount)
                        : "não informado"}
                      {" · assinado "}{formatOptionalDate(contract.signedDate)}
                      {" · vigência "}{formatOptionalDate(contract.effectiveFrom)}
                      {" a "}{formatOptionalDate(contract.effectiveUntil)}
                      {contract.sourceUrl ? (
                        <>
                          {" · "}
                          <a href={contract.sourceUrl} target="_blank" rel="noreferrer">
                            fonte do contrato
                          </a>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
                <p className="meta-note">
                  Este valor é o valor atual informado no contrato pelo PNCP. Ele não
                  representa, sozinho, empenho ou pagamento.
                </p>
              </details>
            ) : null}
          </>
        ) : procurement.executionSummary.state === "no_linked_execution" ? (
          <p className="meta-note">
            Ainda não publicamos vínculos de contrato, empenho, liquidação ou pagamento para esta contratação.
            {" "}O motivo pode ser uma coleta pendente, uma resposta inconclusiva ou a falta de um vínculo validado.
          </p>
        ) : procurement.executionSummary.state === "not_normalized" ? (
          <p className="meta-note">
            Os vínculos desta contratação ainda estão em preparação.
            O registro do PNCP continua disponível na fonte oficial.
          </p>
        ) : (
          <p className="meta-note">
            O resumo dos vínculos não está disponível neste momento.
          </p>
        )}
      </details>
      {procurement.executionSummary.evidenceCount > 0 ? (
        <details className="procurement-evidence">
          <summary>
            Evidências preservadas ({formatCount(procurement.executionSummary.evidenceCount)})
          </summary>
          <ul>
            {procurement.executionSummary.evidence.map((evidence) => (
              <li key={`${evidence.entityType}-${evidence.rawRecordId}`}>
                <strong>{evidenceLabel(evidence.entityType)}</strong>{" · "}
                <a href={evidence.sourceUrl} target="_blank" rel="noreferrer">
                  fonte oficial
                </a>
                {evidence.documentSourceUrl ? (
                  <>
                    {" · "}
                    <a href={evidence.documentSourceUrl} target="_blank" rel="noreferrer">
                      documento oficial
                    </a>
                  </>
                ) : null}
                <span className="evidence-meta">
                  {" · coleta "}{evidence.retrievedAt}{" · hash "}{evidence.sha256}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
        </>
      )}
      <p className="act-evidence">
        {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">
          Ver no PNCP (registro oficial)
        </a> : <span>Link oficial indisponível: identificador não validado</span>}{" "}
        · processo {procurement.controlNumber}
      </p>
      <p className="act-review-mode">
        Dados oficiais do Portal Nacional de Contratações Públicas, exibidos
        sem tratamento editorial. Valores estimados e homologados são os
        informados pelo próprio portal — nada é calculado por nós.
      </p>
    </article>
  );
}

// ponytail: as demais contratações ficam recolhidas, sem nova consulta;
// paginar no banco exigiria offset na RPC get_pncp_procurements_normalized.
const FIRST_VISIBLE = 15;

export function ProcurementExplorer({
  procurements,
}: Readonly<{ procurements: readonly Procurement[] }>) {
  const loadedHomologatedTotal = procurements.reduce(
    (total, procurement) => total + (procurement.valorHomologado ?? 0),
    0,
  );

  return (
    <div className="procurement-explorer">
      <div className="procurement-summary" aria-live="polite">
        <strong>
          {procurements.length} {procurements.length === 1 ? "registro" : "registros"} carregados
        </strong>
        <span>
          {loadedHomologatedTotal > 0
            ? `Soma dos valores homologados carregados: ${currencyFormatter.format(loadedHomologatedTotal)}`
            : "Nenhum valor homologado publicado entre os registros carregados — ausência de valor não significa custo zero."}
        </span>
      </div>
      {procurements.length > 0 ? (
        <p className="meta-note procurement-coverage-note">
          Cada cartão mostra os vínculos publicados na plataforma; isso não confirma que todos os contratos e pagamentos foram coletados.
          {" "}A ausência de um vínculo aqui não prova que ele não exista na fonte oficial.
          {" "}Itens, vencedores, execução e evidências ficam na página de cada contratação.
        </p>
      ) : null}
      {procurements.length > 0 ? (
        <>
          <div className="digest-grid">
            {procurements.slice(0, FIRST_VISIBLE).map((procurement) => (
              <ProcurementCard
                key={procurement.controlNumber}
                procurement={procurement}
                compact
              />
            ))}
          </div>
          {procurements.length > FIRST_VISIBLE ? (
            <details className="procurement-more">
              <summary>
                Ver mais {procurements.length - FIRST_VISIBLE} contratações
              </summary>
              <div className="digest-grid">
                {procurements.slice(FIRST_VISIBLE).map((procurement) => (
                  <ProcurementCard
                    key={procurement.controlNumber}
                    procurement={procurement}
                    compact
                  />
                ))}
              </div>
            </details>
          ) : null}
        </>
      ) : (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Nenhuma contratação corresponde aos filtros</strong>
            <p>
              Ajuste os campos no painel acima. Isso não significa que não existam
              contratações na fonte oficial.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
