import type {
  AnnualExpenseCategoriesResult,
  AnnualExpenseCategory,
} from "../../../../lib/annual-expense-categories.mjs";
import {
  classifyExpenseDescription,
  EXPENSE_CLASSIFICATION_SOURCE_URL,
} from "../../../../lib/expense-classification.mjs";
import { monthlyFinanceHref } from "../../../../lib/monthly-finance-detail.mjs";
import { formatBrlDecimal } from "../../../../lib/revenues";

const PRIMARY_CATEGORY_COUNT = 8;
const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  timeZone: "America/Bahia",
});

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function CategoryRow({ category }: Readonly<{ category: AnnualExpenseCategory }>) {
  const classification = classifyExpenseDescription(
    category.expenseCode,
    category.sourceDescription,
  );
  const numericShare = Number(category.paidSharePercent);
  const shareWidth = Number.isFinite(numericShare)
    ? Math.max(0, Math.min(100, numericShare))
    : 0;

  return (
    <li className="finance-annual-category-row">
      <div className="finance-annual-category-heading">
        <div>
          <span>{category.expenseCode}</span>
          <h3>{classification.displayDescription}</h3>
        </div>
        <p>
          <strong>{formatBrlDecimal(category.paidAmount)}</strong>
          <small>
            {category.paidSharePercent === null
              ? "participação não calculável"
              : `${category.paidSharePercent}% dos meses detalhados`}
          </small>
        </p>
      </div>
      <div
        className="finance-annual-category-track"
        role="img"
        aria-label={category.paidSharePercent === null
          ? "Participação indisponível porque o total reconciliado não é positivo"
          : `${category.paidSharePercent}% dos pagamentos com categorias reconciliadas`}
      >
        <span style={{ width: `${shareWidth}%` }} />
      </div>
      <details className="finance-annual-category-details">
        <summary>Ver evolução mês a mês e documentos</summary>
        <p>
          O total reúne {category.monthCount.toLocaleString("pt-BR")} mês(es) em que
          este código apareceu, com {category.lineCount.toLocaleString("pt-BR")} linha(s)
          contábil(eis). Mês sem detalhamento reconciliado não foi convertido em zero.
        </p>
        <ol className="finance-annual-category-months">
          {category.months.map((month) => (
            <li
              className={month.paidAmount === null ? "finance-annual-category-month-missing" : ""}
              key={month.periodStart}
            >
              <div className="finance-annual-category-month-heading">
                <strong>{formatMonth(month.periodStart)}</strong>
                <a href={monthlyFinanceHref(month.periodStart)}>Abrir mês →</a>
              </div>
              {month.paidAmount === null ? (
                <p>Detalhamento por categoria ainda não reconciliado.</p>
              ) : (
                <>
                  <div className="finance-annual-category-month-track" aria-hidden="true">
                    <span style={{ width: `${(month.barBasisPoints ?? 0) / 100}%` }} />
                  </div>
                  <p className={month.paidAmount.startsWith("-") ? "finance-negative-value" : ""}>
                    <strong>{formatBrlDecimal(month.paidAmount)}</strong>
                    {month.paidAmount === "0.00"
                      ? " · o relatório completo não trouxe este código no mês"
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
        {category.descriptionVariationObserved ? (
          <p>
            Os balancetes registraram variação na descrição deste código ao longo do
            recorte. O agrupamento foi feito pelo código contábil, sem tentar estimar
            quantas grafias únicas existem no ano.
          </p>
        ) : null}
        {classification.classificationStatus === "official_code_match" ? (
          <p>
            Nome completado pelo código exato na classificação oficial do Tesouro.{" "}
            <a href={EXPENSE_CLASSIFICATION_SOURCE_URL} target="_blank" rel="noreferrer">
              Conferir classificação oficial
            </a>
          </p>
        ) : null}
        {classification.classificationStatus === "source_conflict" ? (
          <p className="finance-category-conflict">
            A descrição do balancete não coincide com o rótulo oficial conhecido. Mantivemos
            o texto da Prefeitura e não inferimos outra categoria.
          </p>
        ) : null}
      </details>
    </li>
  );
}

export function FinanceAnnualExpenseCategories({
  result,
}: Readonly<{ result: AnnualExpenseCategoriesResult }>) {
  if (result.state === "conflict") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-category-title">
        <span className="eyebrow">Destino dos pagamentos</span>
        <h2 id="finance-year-category-title">Categorias protegidas por divergência</h2>
        <p>
          Em {formatMonth(result.periodStart)}, o total das linhas não coincidiu com o
          fechamento oficial. Nenhum ranking anual foi publicado até a reconciliação.
        </p>
      </section>
    );
  }

  if (result.state === "unavailable") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-category-title">
        <span className="eyebrow">Destino dos pagamentos</span>
        <h2 id="finance-year-category-title">Detalhamento anual temporariamente indisponível</h2>
        <p>
          Os totais do ano continuam válidos. Apenas o agrupamento por categoria não pôde
          ser montado agora; nenhum valor foi estimado ou substituído por zero.
        </p>
      </section>
    );
  }

  if (result.state === "empty") {
    return (
      <section className="finance-year-category-warning" aria-labelledby="finance-year-category-title">
        <span className="eyebrow">Destino dos pagamentos</span>
        <h2 id="finance-year-category-title">Categorias ainda não publicadas para este ano</h2>
        <p>
          Há {result.comparableMonthCount.toLocaleString("pt-BR")} fechamento(s) mensal(is),
          mas os balancetes ainda não possuem categorias integralmente reconciliadas.
          Isso não significa gasto zero.
        </p>
      </section>
    );
  }

  const primary = result.categories.slice(0, PRIMARY_CATEGORY_COUNT);
  const remaining = result.categories.slice(PRIMARY_CATEGORY_COUNT);

  return (
    <section className="finance-year-category-section" aria-labelledby="finance-year-category-title">
      <div className="section-heading compact">
        <span className="eyebrow">Destino dos pagamentos</span>
        <h2 id="finance-year-category-title">Em que tipos de despesa a Prefeitura pagou</h2>
        <p>
          Ranking calculado sobre {result.categoryCoveredMonthCount} de {result.comparableMonthCount}
          {" "}mês(es) comparáveis. Ele agrupa a natureza contábil do gasto — não secretaria,
          política pública ou fornecedor.
        </p>
      </div>
      <div className="finance-year-category-coverage" role="status">
        <strong>{formatBrlDecimal(result.annualPaidAmount)}</strong>
        <span>em pagamentos com categorias reconciliadas</span>
      </div>
      <ol className="finance-annual-category-list">
        {primary.map((category) => (
          <CategoryRow category={category} key={category.expenseCode} />
        ))}
      </ol>
      {remaining.length > 0 ? (
        <details className="finance-annual-category-more">
          <summary>Ver outras {remaining.length.toLocaleString("pt-BR")} categorias</summary>
          <p>A lista continua do maior para o menor valor líquido pago.</p>
          <ol className="finance-annual-category-list finance-annual-category-list-secondary">
            {remaining.map((category) => (
              <CategoryRow category={category} key={category.expenseCode} />
            ))}
          </ol>
        </details>
      ) : null}
      <p className="finance-annual-method">
        Soma e percentuais calculados em centavos por código determinístico, somente
        após cada balancete reconciliar com seu fechamento. IA não calcula valores.
      </p>
    </section>
  );
}
