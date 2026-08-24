import type {
  ParsedSiconfiAnnualMetric,
  SiconfiAnnualMetricKey,
} from "../../lib/siconfi-annual-totals-parser.mjs";
import type { PublicSiconfiAnnualYear } from "../../lib/siconfi-annual-totals";
import type {
  PublicSiconfiReconciliationYear,
} from "../../lib/siconfi-monthly-reconciliation";
import type {
  ParsedSiconfiReconciliationMetric,
  SiconfiReconciliationMetricKey,
} from "../../lib/siconfi-monthly-reconciliation-parser.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

const LABELS: Record<SiconfiAnnualMetricKey, string> = {
  gross_revenue_realized: "Receita bruta realizada",
  fundeb_deductions: "Dedução para o Fundeb",
  expense_committed: "Despesa empenhada",
  expense_liquidated: "Despesa liquidada",
  expense_paid: "Despesa paga",
  nonprocessed_payables_registered: "Restos a pagar não processados inscritos",
  processed_payables_registered: "Restos a pagar processados inscritos",
};

const EXPLANATIONS: Record<SiconfiAnnualMetricKey, string> = {
  gross_revenue_realized:
    "Quanto a Prefeitura declarou ter arrecadado no ano, antes da dedução do Fundeb.",
  fundeb_deductions:
    "Parcela informada separadamente pelo SICONFI como dedução destinada ao Fundeb.",
  expense_committed:
    "Valor reservado por empenhos. Não significa que todo esse dinheiro já saiu do caixa.",
  expense_liquidated:
    "Parte da despesa cuja entrega ou serviço foi reconhecido pela administração.",
  expense_paid: "Dinheiro que a Prefeitura declarou ter efetivamente pago no ano.",
  nonprocessed_payables_registered:
    "Empenhos inscritos para anos seguintes sem liquidação registrada no encerramento.",
  processed_payables_registered:
    "Despesas já liquidadas, mas ainda não pagas, inscritas para anos seguintes.",
};

function metric(
  year: PublicSiconfiAnnualYear,
  key: SiconfiAnnualMetricKey,
): ParsedSiconfiAnnualMetric {
  const found = year.metrics.find((item) => item.metricKey === key);
  if (!found) throw new Error(`Métrica SICONFI ausente: ${key}`);
  return found;
}

function valueClass(key: SiconfiAnnualMetricKey): string {
  return key === "gross_revenue_realized" ? "finance-positive-value" : "finance-negative-value";
}

function MetricValue({ item }: Readonly<{ item: ParsedSiconfiAnnualMetric }>) {
  return (
    <div className={valueClass(item.metricKey)}>
      <dt>{LABELS[item.metricKey]}</dt>
      <dd>{formatBrlDecimal(item.amount)}</dd>
      <small>{EXPLANATIONS[item.metricKey]}</small>
    </div>
  );
}

const RECONCILIATION_LABELS: Record<SiconfiReconciliationMetricKey, string> = {
  expense_committed: "Empenhado",
  expense_liquidated: "Liquidado",
  expense_paid: "Pago",
};

const MONTH_NAMES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

function missingMonthNames(months: readonly number[]): string {
  return months.map((month) => MONTH_NAMES[month - 1]).join(", ");
}

function reconciliationStatus(item: ParsedSiconfiReconciliationMetric): string {
  if (item.reconciliationStatus === "matched_exact") return "Confere exatamente";
  if (item.reconciliationStatus === "source_difference") {
    return "Há diferença entre as fontes";
  }
  return `Faltam ${12 - item.observedMonths} meses`;
}

function reconciliationClass(item: ParsedSiconfiReconciliationMetric): string {
  return `finance-siconfi-reconciliation-card is-${item.reconciliationStatus}`;
}

export function FinanceSiconfiAnnualTotals({
  years,
  reconciliationYears,
}: Readonly<{
  years: readonly PublicSiconfiAnnualYear[];
  reconciliationYears: readonly PublicSiconfiReconciliationYear[];
}>) {
  if (years.length === 0) return null;
  const [latest, ...history] = years;
  const reconciliation = reconciliationYears.find(
    (year) => year.fiscalYear === latest.fiscalYear,
  );
  const source = latest.metrics[0];
  const mainMetrics: SiconfiAnnualMetricKey[] = [
    "gross_revenue_realized",
    "fundeb_deductions",
    "expense_committed",
    "expense_liquidated",
    "expense_paid",
  ];
  const payableMetrics: SiconfiAnnualMetricKey[] = [
    "nonprocessed_payables_registered",
    "processed_payables_registered",
  ];
  return (
    <section className="finance-siconfi-section" aria-labelledby="siconfi-annual-title">
      <div className="section-heading compact">
        <span className="eyebrow">Ano fechado no Tesouro Nacional</span>
        <h2 id="siconfi-annual-title">O retrato anual oficial das contas</h2>
        <p>
          Estes valores vêm da Declaração das Contas Anuais (DCA) enviada ao
          SICONFI. Cada etapa aparece separada porque empenhar, liquidar e pagar
          não são a mesma coisa.
        </p>
      </div>
      <article className="finance-siconfi-latest">
        <header>
          <div>
            <span>Último exercício com declaração completa</span>
            <h3>{latest.fiscalYear}</h3>
          </div>
          <a href={source.sourceUrl} target="_blank" rel="noreferrer">
            Conferir no SICONFI →
          </a>
        </header>
        <dl className="finance-siconfi-main-grid">
          {mainMetrics.map((key) => <MetricValue key={key} item={metric(latest, key)} />)}
        </dl>
        <details className="finance-details">
          <summary>Ver restos a pagar e detalhes da fonte</summary>
          <dl className="finance-siconfi-payables">
            {payableMetrics.map((key) => <MetricValue key={key} item={metric(latest, key)} />)}
          </dl>
          <p className="act-evidence">
            Resposta oficial preservada · hash {source.sourceArtifactSha256.slice(0, 12)}…
            · método {source.methodologyVersion}. Nenhuma IA calculou estes valores.
          </p>
        </details>
      </article>
      {reconciliation ? (
        <section
          className="finance-siconfi-reconciliation"
          aria-labelledby="siconfi-reconciliation-title"
        >
          <header>
            <div>
              <span className="eyebrow">Conferência entre fontes oficiais</span>
              <h3 id="siconfi-reconciliation-title">
                Os 12 meses conferem com o ano de {reconciliation.fiscalYear}?
              </h3>
            </div>
            <p>
              Somamos por código os doze relatórios mensais e comparamos com a
              declaração anual do Tesouro. Receita não entra nesta comparação
              porque os relatórios usam conceitos diferentes.
            </p>
          </header>
          <div className="finance-siconfi-reconciliation-grid">
            {reconciliation.metrics.map((item) => (
              <article className={reconciliationClass(item)} key={item.metricKey}>
                <span>{RECONCILIATION_LABELS[item.metricKey]}</span>
                <strong>{reconciliationStatus(item)}</strong>
                {item.monthlySumAmount && item.differenceAmount ? (
                  <dl>
                    <div>
                      <dt>Declaração anual</dt>
                      <dd>{formatBrlDecimal(item.annualAmount)}</dd>
                    </div>
                    <div>
                      <dt>Soma dos 12 meses</dt>
                      <dd>{formatBrlDecimal(item.monthlySumAmount)}</dd>
                    </div>
                    <div>
                      <dt>Diferença anual − mensais</dt>
                      <dd>{formatBrlDecimal(item.differenceAmount)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p>
                    Foram localizados {item.observedMonths} de 12 meses. Meses
                    ausentes: {missingMonthNames(item.missingMonths)}. Isso não
                    significa gasto zero: o documento oficial mensal não foi validado
                    no portal da Prefeitura, então nenhum total parcial é exibido.
                  </p>
                )}
                <details>
                  <summary>Entender este resultado</summary>
                  <p>{item.reconciliationNote}</p>
                  <small>Método determinístico {item.methodologyVersion}</small>
                </details>
              </article>
            ))}
          </div>
          <p className="finance-siconfi-reconciliation-caution">
            Diferença entre fontes não é prova de irregularidade. Pode decorrer
            de ajustes de encerramento, restos a pagar ou atualização posterior
            de um relatório. O Barreiras 360 mostra a divergência para que ela
            possa ser conferida — não inventa uma explicação.
          </p>
        </section>
      ) : null}
      {history.length > 0 ? (
        <details className="finance-details finance-siconfi-history">
          <summary>Comparar com {history.length} anos anteriores</summary>
          <div className="finance-siconfi-history-list">
            {history.map((year) => (
              <article key={year.fiscalYear}>
                <h3>{year.fiscalYear}</h3>
                <dl>
                  <MetricValue item={metric(year, "gross_revenue_realized")} />
                  <MetricValue item={metric(year, "expense_paid")} />
                  <MetricValue item={metric(year, "fundeb_deductions")} />
                </dl>
                <a href={year.metrics[0].sourceUrl} target="_blank" rel="noreferrer">
                  Abrir fonte oficial →
                </a>
              </article>
            ))}
          </div>
        </details>
      ) : null}
      {reconciliationYears.length > 1 ? (
        <details className="finance-details finance-siconfi-reconciliation-history">
          <summary>Ver a conferência dos anos anteriores</summary>
          <div className="finance-siconfi-reconciliation-history-list">
            {reconciliationYears.slice(1).map((year) => (
              <article key={year.fiscalYear}>
                <header>
                  <h3>{year.fiscalYear}</h3>
                  <span>{year.metrics[0]?.observedMonths ?? 0} de 12 meses</span>
                </header>
                <ul>
                  {year.metrics.map((item) => (
                    <li key={item.metricKey}>
                      <div>
                        <span>{RECONCILIATION_LABELS[item.metricKey]}</span>
                        <strong>{reconciliationStatus(item)}</strong>
                      </div>
                      {item.monthlySumAmount && item.differenceAmount ? (
                        <details>
                          <summary>Ver valores comparados</summary>
                          <p>
                            Ano: {formatBrlDecimal(item.annualAmount)} · 12 meses:{" "}
                            {formatBrlDecimal(item.monthlySumAmount)} · diferença:{" "}
                            {formatBrlDecimal(item.differenceAmount)}.
                          </p>
                        </details>
                      ) : (
                        <p>
                          Não comparado. Meses ausentes:{" "}
                          {missingMonthNames(item.missingMonths)}.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </details>
      ) : null}
      <p className="finance-annual-method">
        Não subtraímos automaticamente a dedução do Fundeb da receita bruta e
        não chamamos a diferença entre receita e pagamento de superávit ou déficit.
        Essa interpretação exige reconciliação contábil adicional.
      </p>
    </section>
  );
}
