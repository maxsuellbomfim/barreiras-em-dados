import type { PublicSiconfiAnnualYear } from "../../../../lib/siconfi-annual-totals";
import type { PublicSiconfiReconciliationYear } from "../../../../lib/siconfi-monthly-reconciliation";
import type {
  ParsedSiconfiReconciliationMetric,
  SiconfiReconciliationMetricKey,
} from "../../../../lib/siconfi-monthly-reconciliation-parser.mjs";
import { formatBrlDecimal } from "../../../../lib/revenues";

const STAGE_LABELS: Record<SiconfiReconciliationMetricKey, string> = {
  expense_committed: "Empenhado",
  expense_liquidated: "Liquidado",
  expense_paid: "Pago",
};

const ANNUAL_LABELS = {
  gross_revenue_realized: "Receita bruta realizada",
  fundeb_deductions: "Dedução para o Fundeb",
  expense_committed: "Despesa empenhada",
  expense_liquidated: "Despesa liquidada",
  expense_paid: "Despesa paga",
  nonprocessed_payables_registered: "Restos a pagar não processados inscritos",
  processed_payables_registered: "Restos a pagar processados inscritos",
} as const;

const MONTH_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  timeZone: "America/Bahia",
});

function monthNames(months: readonly number[]): string {
  return months
    .map((month) => MONTH_FORMATTER.format(new Date(`2026-${String(month).padStart(2, "0")}-15T12:00:00-03:00`)))
    .join(", ");
}

function statusLabel(item: ParsedSiconfiReconciliationMetric): string {
  if (item.reconciliationStatus === "matched_exact") return "Confere exatamente";
  if (item.reconciliationStatus === "source_difference") {
    return "Diferença entre fontes";
  }
  return `${item.observedMonths} de 12 meses localizados`;
}

export function FinanceYearSiconfi({
  fiscalYear,
  annualYear,
  reconciliationYear,
}: Readonly<{
  fiscalYear: number;
  annualYear: PublicSiconfiAnnualYear | null;
  reconciliationYear: PublicSiconfiReconciliationYear | null;
}>) {
  if (!annualYear) {
    return (
      <section className="finance-year-siconfi is-unavailable" aria-labelledby="year-siconfi-title">
        <span className="eyebrow">Declaração anual ao Tesouro</span>
        <h2 id="year-siconfi-title">DCA de {fiscalYear} ainda não localizada</h2>
        <p>
          Isso não significa receita ou despesa zero. O Barreiras 360 não
          encontrou uma declaração anual completa e validada para este exercício
          na fonte consultada; os fechamentos mensais continuam visíveis abaixo.
        </p>
      </section>
    );
  }

  const source = annualYear.metrics[0];
  const mainMetrics = annualYear.metrics.filter((item) =>
    [
      "gross_revenue_realized",
      "expense_committed",
      "expense_liquidated",
      "expense_paid",
    ].includes(item.metricKey),
  );
  const detailMetrics = annualYear.metrics.filter(
    (item) => !mainMetrics.includes(item),
  );

  return (
    <section className="finance-year-siconfi" aria-labelledby="year-siconfi-title">
      <header>
        <div>
          <span className="eyebrow">Declaração anual ao Tesouro</span>
          <h2 id="year-siconfi-title">O que a Prefeitura declarou no ano</h2>
        </div>
        <a href={source.sourceUrl} target="_blank" rel="noreferrer">
          Conferir no SICONFI →
        </a>
      </header>

      <dl className="finance-year-siconfi-totals">
        {mainMetrics.map((item) => (
          <div key={item.metricKey}>
            <dt>{ANNUAL_LABELS[item.metricKey]}</dt>
            <dd>{formatBrlDecimal(item.amount)}</dd>
          </div>
        ))}
      </dl>

      {reconciliationYear ? (
        <div className="finance-year-siconfi-check">
          <h3>A soma dos meses confere com o ano?</h3>
          <p>
            Conferência por código dos três estágios da despesa. Receita não é
            comparada porque as duas séries oficiais podem usar conceitos diferentes.
          </p>
          <ul>
            {reconciliationYear.metrics.map((item) => (
              <li className={`is-${item.reconciliationStatus}`} key={item.metricKey}>
                <div>
                  <span>{STAGE_LABELS[item.metricKey]}</span>
                  <strong>{statusLabel(item)}</strong>
                </div>
                {item.monthlySumAmount && item.differenceAmount ? (
                  <details>
                    <summary>Ver números</summary>
                    <dl>
                      <div><dt>DCA anual</dt><dd>{formatBrlDecimal(item.annualAmount)}</dd></div>
                      <div><dt>12 meses</dt><dd>{formatBrlDecimal(item.monthlySumAmount)}</dd></div>
                      <div><dt>Diferença</dt><dd>{formatBrlDecimal(item.differenceAmount)}</dd></div>
                    </dl>
                    <p>{item.reconciliationNote}</p>
                  </details>
                ) : (
                  <p>
                    Não há comparação parcial. Meses ausentes: {monthNames(item.missingMonths)}.
                  </p>
                )}
              </li>
            ))}
          </ul>
          <p className="finance-year-siconfi-caution">
            Diferença entre fontes não prova irregularidade. Ela fica exposta
            para conferência documental e pode refletir ajustes de encerramento.
          </p>
        </div>
      ) : (
        <div className="finance-year-siconfi-check is-unavailable" role="status">
          <h3>Conferência mensal ainda não disponível</h3>
          <p>
            A declaração anual foi localizada, mas a comparação com os doze
            meses não está publicada. Isso não significa que os valores conferem
            ou divergem; significa apenas que a verificação ainda não foi obtida.
          </p>
        </div>
      )}

      <details className="finance-details finance-year-siconfi-details">
        <summary>Ver Fundeb, restos a pagar e evidência</summary>
        <dl>
          {detailMetrics.map((item) => (
            <div key={item.metricKey}>
              <dt>{ANNUAL_LABELS[item.metricKey]}</dt>
              <dd>{formatBrlDecimal(item.amount)}</dd>
            </div>
          ))}
        </dl>
        <p>
          Resposta oficial preservada · hash {source.sourceArtifactSha256.slice(0, 12)}…
          · método {source.methodologyVersion}. Nenhuma IA somou ou comparou valores.
        </p>
      </details>
    </section>
  );
}
