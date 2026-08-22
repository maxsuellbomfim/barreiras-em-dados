import type { ExpenseCategoryMonthComparison } from "../../lib/expense-category-comparison.mjs";
import {
  classifyExpenseDescription,
} from "../../lib/expense-classification.mjs";
import { monthlyFinanceHref } from "../../lib/monthly-finance-detail.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function variationCopy(value: string): string {
  if (value.startsWith("-")) return "diminuiu";
  if (value === "0.00") return "não mudou";
  return "aumentou";
}

function variationClass(value: string): string {
  return value.startsWith("-")
    ? "finance-positive-value"
    : value === "0.00"
      ? ""
      : "finance-negative-value";
}

export function FinanceExpenseMonthComparison({
  result,
  currentPeriodStart,
  previousPeriodStart,
}: Readonly<{
  result: ExpenseCategoryMonthComparison;
  currentPeriodStart: string;
  previousPeriodStart: string;
}>) {
  if (result.state !== "available") return null;

  return (
    <section className="finance-month-comparison" aria-labelledby="finance-comparison-title">
      <div className="section-heading compact">
        <span className="eyebrow">Mudança mês a mês</span>
        <h2 id="finance-comparison-title">
          Comparação com {formatMonth(previousPeriodStart)}
        </h2>
        <p>
          Comparamos apenas relatórios completos e reconciliados do mês imediatamente
          anterior. Nenhuma IA calculou ou alterou estes valores.
        </p>
      </div>

      <div className="finance-comparison-total">
        <div><span>Mês anterior</span><strong>{formatBrlDecimal(result.previousTotalPaidAmount)}</strong></div>
        <div><span>{formatMonth(currentPeriodStart)}</span><strong>{formatBrlDecimal(result.currentTotalPaidAmount)}</strong></div>
        <div className={variationClass(result.totalDifferenceAmount)}>
          <span>O total pago {variationCopy(result.totalDifferenceAmount)}</span>
          <strong>{formatBrlDecimal(result.totalDifferenceAmount)}</strong>
        </div>
      </div>

      <details className="finance-comparison-details">
        <summary>Ver a mudança nas cinco maiores categorias atuais</summary>
        <ol>
          {result.categories.map((category) => {
            const classification = classifyExpenseDescription(
              category.expenseCode,
              category.sourceDescription,
            );
            return (
              <li key={category.expenseCode}>
                <div>
                  <span>{category.expenseCode}</span>
                  <strong>{classification.displayDescription}</strong>
                </div>
                <p><span>Mês atual</span>{formatBrlDecimal(category.currentPaidAmount)}</p>
                {category.previousPaidAmount === null || category.differenceAmount === null ? (
                  <p className="finance-comparison-missing">
                    Esta categoria não foi localizada no relatório anterior; não foi
                    convertida em valor zero.
                  </p>
                ) : (
                  <p className={variationClass(category.differenceAmount)}>
                    <span>{variationCopy(category.differenceAmount)} desde o mês anterior</span>
                    {formatBrlDecimal(category.differenceAmount)}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      </details>
      <a className="finance-comparison-link" href={monthlyFinanceHref(previousPeriodStart)}>
        Ver as contas de {formatMonth(previousPeriodStart)} →
      </a>
    </section>
  );
}
