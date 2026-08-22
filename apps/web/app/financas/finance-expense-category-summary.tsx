import type {
  ExpenseCategorySummaryResult,
  PublicExpenseCategory,
} from "../../lib/expense-category-summary.mjs";
import {
  classifyExpenseDescription,
  EXPENSE_CLASSIFICATION_SOURCE_URL,
} from "../../lib/expense-classification.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

function CategoryRow({ category }: Readonly<{ category: PublicExpenseCategory }>) {
  const classification = classifyExpenseDescription(
    category.expenseCode,
    category.sourceDescription,
  );
  const numericShare = Number(category.paidSharePercent);
  const barWidth = Number.isFinite(numericShare)
    ? Math.max(0, Math.min(100, numericShare))
    : 0;

  return (
    <li className="finance-category-row">
      <div className="finance-category-heading">
        <div>
          <span>{category.expenseCode}</span>
          <h3>{classification.displayDescription}</h3>
        </div>
        <p>
          <strong>{formatBrlDecimal(category.paidPeriodAmount)}</strong>
          <small>{category.paidSharePercent}% do total pago</small>
        </p>
      </div>
      <div
        className="finance-category-track"
        role="img"
        aria-label={`${category.paidSharePercent}% do total pago no relatório`}
      >
        <span style={{ width: `${barWidth}%` }} />
      </div>
      <details className="finance-category-details">
        <summary>Entender esta categoria</summary>
        <dl>
          <div><dt>Empenhado</dt><dd>{formatBrlDecimal(category.committedPeriodAmount)}</dd></div>
          <div><dt>Liquidado</dt><dd>{formatBrlDecimal(category.liquidatedPeriodAmount)}</dd></div>
          <div><dt>Pago</dt><dd>{formatBrlDecimal(category.paidPeriodAmount)}</dd></div>
          <div><dt>Linhas agrupadas</dt><dd>{category.lineCount.toLocaleString("pt-BR")}</dd></div>
        </dl>
        <p>
          O código agrupou todas as linhas com esta classificação. Ele não somou
          empenho, liquidação e pagamento: os três valores são etapas diferentes.
        </p>
        {category.sourceDescriptionCount > 1 ? (
          <p>
            O PDF usou {category.sourceDescriptionCount.toLocaleString("pt-BR")} grafias
            para o mesmo código contábil. O agrupamento foi feito pelo código, não por
            semelhança de texto.
          </p>
        ) : null}
        {classification.classificationStatus === "official_code_match" ? (
          <p>
            Nome oficial completado pelo código exato na classificação do Tesouro.
            {classification.sourceWasTruncated
              ? ` No PDF municipal aparece apenas “${classification.sourceDescription}”.`
              : ""}{" "}
            <a href={EXPENSE_CLASSIFICATION_SOURCE_URL} target="_blank" rel="noreferrer">
              Conferir classificação oficial
            </a>
          </p>
        ) : null}
        {classification.classificationStatus === "source_conflict" ? (
          <p className="finance-category-conflict">
            A descrição do PDF não coincide com o rótulo oficial conhecido para este
            código. Mantivemos literalmente o texto da Prefeitura e não inferimos outro.
          </p>
        ) : null}
      </details>
    </li>
  );
}

export function FinanceExpenseCategorySummary({
  result,
}: Readonly<{ result: ExpenseCategorySummaryResult }>) {
  if (result.state === "conflict") {
    return (
      <section className="finance-category-warning" aria-labelledby="finance-category-warning-title">
        <span className="eyebrow">Detalhamento protegido</span>
        <h2 id="finance-category-warning-title">As categorias não foram exibidas</h2>
        <p>
          A soma das linhas ({formatBrlDecimal(result.aggregatedTotalPaidAmount)}) não
          coincide com o total pago do relatório ({formatBrlDecimal(result.reportTotalPaidAmount)}).
          O Barreiras 360 não publica percentuais enquanto essa diferença não for
          reconciliada com o documento oficial.
        </p>
      </section>
    );
  }
  if (result.state !== "available" || result.categories.length === 0) return null;

  const lineCount = result.categories.reduce(
    (total, category) => total + category.lineCount,
    0,
  );

  return (
    <section className="finance-category-section" aria-labelledby="finance-category-title">
      <div className="section-heading compact">
        <span className="eyebrow">Para onde foi o dinheiro</span>
        <h2 id="finance-category-title">Despesas agrupadas por tipo</h2>
        <p>
          Este quadro usa todas as linhas contábeis do relatório — {lineCount.toLocaleString("pt-BR")}
          {" "}linha(s), agrupadas em {result.categories.length.toLocaleString("pt-BR")} categoria(s).
          Os valores são grupos contábeis e não são pagamentos individuais nem um
          ranking de empresas.
        </p>
      </div>
      <ol className="finance-category-list">
        {result.categories.map((category) => (
          <CategoryRow category={category} key={category.expenseCode} />
        ))}
      </ol>
      <p className="finance-category-method">
        Percentuais calculados no PostgreSQL com decimal exato após a soma das linhas
        coincidir com o total pago do relatório. Nenhuma IA calculou ou alterou valores.
      </p>
    </section>
  );
}
