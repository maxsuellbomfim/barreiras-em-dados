import type { Procurement } from "../../lib/pncp-procurements";

const BARREIRAS_CNPJ = "13654405000195";

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

function pncpUrl(procurement: Procurement) {
  return (
    "https://pncp.gov.br/app/editais/" +
    `${BARREIRAS_CNPJ}/${procurement.ano}/${procurement.sequencial}`
  );
}

function ProcurementCard({ procurement }: Readonly<{ procurement: Procurement }>) {
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
      <h2 className="procurement-object">{procurement.objeto}</h2>
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
              </li>
            ))}
          </ul>
          <p className="meta-note">
            Itens e valores são os informados pelo PNCP. Não comparamos preços nem
            inferimos irregularidade a partir deste registro.
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
      <details className="procurement-execution">
        <summary>Execução financeira ligada</summary>
        {procurement.executionSummary.state === "linked" ? (
          <>
            <p className="meta-note">
              Registros normalizados encontrados pelo identificador oficial da contratação.
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
            A contratação foi normalizada, mas ainda não há contrato, empenho,
            liquidação ou pagamento vinculado por identificador oficial. Isso não
            significa que a despesa não exista.
          </p>
        ) : procurement.executionSummary.state === "not_normalized" ? (
          <p className="meta-note">
            A execução financeira ainda não foi normalizada para esta contratação.
            O registro do PNCP continua disponível na fonte oficial.
          </p>
        ) : (
          <p className="meta-note">
            O resumo de execução será exibido quando a versão pública do vínculo
            estiver disponível.
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
      <p className="act-evidence">
        <a href={pncpUrl(procurement)} target="_blank" rel="noreferrer">
          Ver no PNCP (registro oficial)
        </a>{" "}
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
          Soma dos valores homologados carregados: {currencyFormatter.format(loadedHomologatedTotal)}
        </span>
      </div>
      {procurements.length > 0 ? (
        <div className="digest-grid">
          {procurements.map((procurement) => (
            <ProcurementCard
              key={procurement.controlNumber}
              procurement={procurement}
            />
          ))}
        </div>
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
