import {
  EXPENSE_CLASSIFICATION_SOURCE_URL,
  classifyExpenseDescription,
} from "../../lib/expense-classification.mjs";
import type { PublicExpenseLine } from "../../lib/expenses";
import { formatBrlDecimal } from "../../lib/revenues";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

type FinanceExpenseLineCardProps = Readonly<{
  line: PublicExpenseLine;
  context?: "month" | "period";
  showPeriod?: boolean;
}>;

export function FinanceExpenseLineCard({
  line,
  context = "period",
  showPeriod = false,
}: FinanceExpenseLineCardProps) {
  const classification = classifyExpenseDescription(
    line.expenseCode,
    line.description,
  );
  const suffix = context === "month" ? "neste mês" : "no período";

  return (
    <article className="digest-card finance-negative-card">
      <div className="track-top">
        <span>Linha {line.lineNumber.toLocaleString("pt-BR")}</span>
        <span className="track-status">{line.expenseCode}</span>
      </div>
      <h3 className="procurement-object">{classification.displayDescription}</h3>
      {classification.sourceWasTruncated ? (
        <details className="finance-line-description-note">
          <summary>A descrição veio cortada no PDF da Prefeitura</summary>
          <p>
            O relatório mostra literalmente “{classification.sourceDescription}”.
            A denominação completa acima foi identificada pela correspondência exata
            do código {line.expenseCode}, sem uso de IA.
          </p>
          <a
            href={EXPENSE_CLASSIFICATION_SOURCE_URL}
            target="_blank"
            rel="noreferrer"
          >
            Consultar a classificação oficial do Tesouro Nacional
          </a>
        </details>
      ) : null}
      {classification.classificationStatus === "source_conflict" ? (
        <p className="finance-line-description-conflict" role="status">
          A descrição foi mantida exatamente como publicada porque não coincidiu
          com a denominação padronizada do código.
        </p>
      ) : null}
      <dl className="procurement-values">
        <div className="revenue-primary-value">
          <dt>Pago {suffix}</dt>
          <dd>{formatBrlDecimal(line.paidPeriodAmount)}</dd>
        </div>
        <div>
          <dt>Valor atualizado</dt>
          <dd>{formatBrlDecimal(line.updatedAmount)}</dd>
        </div>
        <div>
          <dt>Empenhado {suffix}</dt>
          <dd>{formatBrlDecimal(line.committedPeriodAmount)}</dd>
        </div>
        <div>
          <dt>Liquidado {suffix}</dt>
          <dd>{formatBrlDecimal(line.liquidatedPeriodAmount)}</dd>
        </div>
      </dl>
      <p className="act-evidence">
        Código da fonte {line.sourceCode}
        {showPeriod ? (
          <> · período {formatDate(line.periodStart)} a {formatDate(line.periodEnd)}</>
        ) : null}{" "}
        ·{" "}
        <a href={line.documentSourceUrl} target="_blank" rel="noreferrer">
          conferir no documento oficial
        </a>
      </p>
    </article>
  );
}
