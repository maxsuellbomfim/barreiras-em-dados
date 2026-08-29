import type {
  AnnualExpenseBudgetUnit,
  AnnualExpenseBudgetUnitsResult,
} from "../../../../lib/annual-expense-budget-units.mjs";
import { monthlyFinanceHref } from "../../../../lib/monthly-finance-detail.mjs";
import { formatBrlDecimal } from "../../../../lib/revenues";

const PRIMARY_UNIT_COUNT = 8;
const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  timeZone: "America/Bahia",
});

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function BudgetUnitRow({ unit }: Readonly<{ unit: AnnualExpenseBudgetUnit }>) {
  const numericShare = Number(unit.paidSharePercent);
  const shareWidth = Number.isFinite(numericShare)
    ? Math.max(0, Math.min(100, numericShare))
    : 0;
  return (
    <li className="finance-annual-category-row">
      <div className="finance-annual-category-heading">
        <div>
          <span>Unidade {unit.budgetUnitCode}</span>
          <h3>{unit.budgetUnitName}</h3>
        </div>
        <p>
          <strong>{formatBrlDecimal(unit.paidAmount)}</strong>
          <small>
            {unit.paidSharePercent === null
              ? "participação não calculável"
              : `${unit.paidSharePercent}% dos meses detalhados`}
          </small>
        </p>
      </div>
      <div
        className="finance-annual-category-track"
        role="img"
        aria-label={unit.paidSharePercent === null
          ? "Participação indisponível porque o total reconciliado não é positivo"
          : `${unit.paidSharePercent}% dos pagamentos atribuídos a unidades orçamentárias`}
      >
        <span style={{ width: `${shareWidth}%` }} />
      </div>
      <details className="finance-annual-category-details">
        <summary>Ver evolução mês a mês e documentos</summary>
        <p>
          O total reúne {unit.monthCount.toLocaleString("pt-BR")} mês(es) em que a
          unidade apareceu, com {unit.lineCount.toLocaleString("pt-BR")} linha(s)
          contábil(eis). Mês sem atribuição integral não foi convertido em zero.
        </p>
        <ol className="finance-annual-category-months">
          {unit.months.map((month) => (
            <li
              className={month.paidAmount === null ? "finance-annual-category-month-missing" : ""}
              key={month.periodStart}
            >
              <div className="finance-annual-category-month-heading">
                <strong>{formatMonth(month.periodStart)}</strong>
                <a href={monthlyFinanceHref(month.periodStart)}>Abrir mês →</a>
              </div>
              {month.paidAmount === null ? (
                <p>Atribuição por unidade ainda não reconciliada neste mês.</p>
              ) : (
                <>
                  <div className="finance-annual-category-month-track" aria-hidden="true">
                    <span style={{ width: `${(month.barBasisPoints ?? 0) / 100}%` }} />
                  </div>
                  <p className={month.paidAmount.startsWith("-") ? "finance-negative-value" : ""}>
                    <strong>{formatBrlDecimal(month.paidAmount)}</strong>
                    {month.paidAmount === "0.00"
                      ? " · o balancete integral não trouxe esta unidade no mês"
                      : " · valor pago registrado"}
                  </p>
                  {month.documentSourceUrl && month.documentArtifactSha256 ? (
                    <p className="act-evidence">
                      <a href={month.documentSourceUrl} target="_blank" rel="noreferrer">
                        Abrir balancete oficial →
                      </a>{" "}
                      · hash {month.documentArtifactSha256.slice(0, 12)}…
                    </p>
                  ) : null}
                </>
              )}
            </li>
          ))}
        </ol>
      </details>
    </li>
  );
}

export function FinanceAnnualBudgetUnits({
  result,
}: Readonly<{ result: AnnualExpenseBudgetUnitsResult }>) {
  if (result.state === "conflict") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-unit-title">
        <span className="eyebrow">Responsabilidade administrativa</span>
        <h2 id="finance-year-unit-title">Unidades protegidas por divergência</h2>
        <p>
          Em {formatMonth(result.periodStart)}, o relatório apresentou uma divergência de
          total ou identificação. Nenhum ranking foi publicado até a reconciliação.
        </p>
      </section>
    );
  }
  if (result.state === "unavailable") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-unit-title">
        <span className="eyebrow">Responsabilidade administrativa</span>
        <h2 id="finance-year-unit-title">Detalhamento por unidade temporariamente indisponível</h2>
        <p>Os totais permanecem válidos; nenhuma secretaria foi estimada e nenhum valor virou zero.</p>
      </section>
    );
  }
  if (result.state === "empty") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-unit-title">
        <span className="eyebrow">Responsabilidade administrativa</span>
        <h2 id="finance-year-unit-title">Unidades ainda não publicadas para este ano</h2>
        <p>
          Há {result.comparableMonthCount.toLocaleString("pt-BR")} fechamento(s), mas
          os balancetes ainda não foram integralmente atribuídos. Isso não significa gasto zero.
        </p>
      </section>
    );
  }

  const primary = result.budgetUnits.slice(0, PRIMARY_UNIT_COUNT);
  const remaining = result.budgetUnits.slice(PRIMARY_UNIT_COUNT);
  return (
    <section className="finance-year-category-section" aria-labelledby="finance-year-unit-title">
      <div className="section-heading compact">
        <span className="eyebrow">Responsabilidade administrativa</span>
        <h2 id="finance-year-unit-title">Pagamentos por unidade orçamentária</h2>
        <p>
          A unidade orçamentária é o órgão, secretaria, fundo ou gabinete indicado em cada
          linha do balancete. Isso mostra a responsabilidade contábil registrada.
          Não significa que o titular da unidade gastou pessoalmente o valor nem
          avalia a qualidade do gasto.
        </p>
      </div>
      <div className="finance-year-category-coverage" role="status">
        <strong>{formatBrlDecimal(result.annualPaidAmount)}</strong>
        <span>
          atribuídos em {result.unitCoveredMonthCount} de {result.comparableMonthCount} mês(es) comparáveis
        </span>
      </div>
      <ol className="finance-annual-category-list">
        {primary.map((unit) => <BudgetUnitRow key={unit.budgetUnitCode} unit={unit} />)}
      </ol>
      {remaining.length > 0 ? (
        <details className="finance-annual-category-more">
          <summary>Ver outras {remaining.length.toLocaleString("pt-BR")} unidades</summary>
          <p>A lista continua do maior para o menor valor líquido pago.</p>
          <ol className="finance-annual-category-list finance-annual-category-list-secondary">
            {remaining.map((unit) => <BudgetUnitRow key={unit.budgetUnitCode} unit={unit} />)}
          </ol>
        </details>
      ) : null}
      <p className="finance-annual-method">
        Este balancete não identifica empenhos individuais e, por isso, não liga esta unidade
        a contratos ou fornecedores. Esse vínculo só será exibido quando uma fonte oficial
        trouxer o número oficial do empenho em ambos os registros.
      </p>
      <p className="finance-annual-method">
        Soma e percentuais calculados em centavos por código determinístico, com o nome
        literal do balancete e vínculo ao PDF preservado. IA não calcula valores.
      </p>
    </section>
  );
}
