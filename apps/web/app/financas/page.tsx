import type { Metadata } from "next";

import {
  getPublicExpenseLines,
  getPublicExpenseReports,
  type PublicExpenseReport,
} from "../../lib/expenses";
import {
  financeResourceLabel,
  getPublicFinanceDocuments,
} from "../../lib/finance-documents";
import {
  formatBrlDecimal,
  getPublicRevenues,
  type PublicRevenue,
} from "../../lib/revenues";
import {
  getPublicMonthlyFinanceClosures,
  type PublicMonthlyFinanceClosure,
} from "../../lib/monthly-finance";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Finanças públicas",
  description:
    "Receitas, despesas e documentos financeiros municipais com fonte verificável.",
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "data não informada";
  const parsed = new Date(`${value}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function formatCollectedAt(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function sortableDate(value: string | null): number | null {
  if (!value) return null;
  const brazilianDate = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (brazilianDate) {
    const [, day, month, year] = brazilianDate;
    return Date.UTC(Number(year), Number(month) - 1, Number(day));
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function sortNewest<T extends { revenueDate?: string | null; referenceDate?: string | null; collectedAt: string }>(
  rows: readonly T[],
  dateKey: "revenueDate" | "referenceDate",
): T[] {
  return [...rows].sort((left, right) => {
    const leftDate = sortableDate(left[dateKey] ?? null) ?? sortableDate(left.collectedAt) ?? 0;
    const rightDate = sortableDate(right[dateKey] ?? null) ?? sortableDate(right.collectedAt) ?? 0;
    return rightDate - leftDate;
  });
}

function explainRevenue(revenue: PublicRevenue): string {
  if (revenue.collectionDirection === "deduction") {
    return `Este registro é uma dedução de ${formatBrlDecimal(revenue.collectedAmount)} no período. Ela aparece com sinal negativo para não ser confundida com arrecadação bruta.`;
  }
  return `Este registro representa ${formatBrlDecimal(revenue.collectedAmount)} arrecadados no período. O acumulado informado no relatório é ${formatBrlDecimal(revenue.accumulatedAmount)}.`;
}

function formatPeriod(report: PublicExpenseReport): string {
  return `${formatDate(report.periodStart)} a ${formatDate(report.periodEnd)}`;
}

function formatMonthTitle(value: string): string {
  const parsed = new Date(`${value}T12:00:00-03:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

function closureStatusLabel(status: PublicMonthlyFinanceClosure["closureStatus"]): string {
  if (status === "operational") return "Fechamento operacional disponível";
  if (status === "needs_review") return "Fechamento aguardando reconciliação";
  return "Fechamento parcial";
}

function explainClosure(closure: PublicMonthlyFinanceClosure): string {
  if (closure.closureStatus === "operational" && closure.operationalDifferenceAmount) {
    const direction = closure.operationalDifferenceAmount.startsWith("-")
      ? "ficou abaixo"
      : "ficou acima";
    return `A receita total declarada no relatório ${direction} dos pagamentos efetivados em ${formatMonthTitle(closure.periodEnd)}. Esta é uma diferença operacional, não uma conclusão de superávit ou déficit fiscal.`;
  }
  return closure.coverageNote;
}

export default async function FinancesPage() {
  const [expensesResult, expenseLinesResult, revenuesResult, documentsResult, monthlyResult] = await Promise.all([
    getPublicExpenseReports(),
    getPublicExpenseLines(),
    getPublicRevenues(),
    getPublicFinanceDocuments(),
    getPublicMonthlyFinanceClosures(),
  ]);
  const expenseReports =
    expensesResult.state === "available" ? expensesResult.reports : [];
  const expenseLines =
    expenseLinesResult.state === "available" ? expenseLinesResult.lines : [];
  const revenues =
    revenuesResult.state === "available" ? revenuesResult.revenues : [];
  const documents =
    documentsResult.state === "available" ? documentsResult.documents : [];
  const monthlyClosures =
    monthlyResult.state === "available" ? monthlyResult.closures : [];
  const sortedRevenues = sortNewest(revenues, "revenueDate");
  const sortedDocuments = sortNewest(documents, "referenceDate");
  const sortedExpenseReports = [...expenseReports].sort((left, right) =>
    right.periodEnd.localeCompare(left.periodEnd),
  );
  const latestRevenue = sortedRevenues[0]?.revenueDate ?? null;

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/licitacoes">Compras</a>
            <a href="/representantes">Quem decide</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="finances-title">
        <div className="section-heading">
          <span className="eyebrow">Dinheiro público</span>
          <h1 id="finances-title">Finanças públicas, sem esconder a conta.</h1>
          <p>
            Acompanhe receitas já normalizadas e os documentos oficiais que
            registram arrecadação, despesas, transferências e relatórios fiscais.
            Quando um valor ainda estiver em um PDF, mostramos o documento e
            deixamos explícito que a extração numérica ainda não foi validada.
          </p>
        </div>

        <section className="finance-guide" aria-labelledby="finance-guide-title">
          <div className="section-heading compact">
            <span className="eyebrow">Em palavras simples</span>
            <h2 id="finance-guide-title">O que cada número quer dizer</h2>
            <p>
              A Prefeitura registra uma despesa em etapas. Elas não são o mesmo
              dinheiro e não devem ser somadas.
            </p>
          </div>
          <div className="finance-guide-grid">
            <article>
              <strong>Orçamento atualizado</strong>
              <p>O limite de gasto depois dos ajustes do ano. Não significa que esse valor já foi gasto.</p>
            </article>
            <article>
              <strong>Reservado</strong>
              <p>Valor separado para uma contratação ou outra despesa. No relatório, aparece como empenhado.</p>
            </article>
            <article>
              <strong>Conferido</strong>
              <p>Parte que já teve entrega ou serviço verificado. É a etapa liquidada.</p>
            </article>
            <article>
              <strong>Pago</strong>
              <p>Dinheiro que efetivamente saiu do caixa no período informado.</p>
            </article>
          </div>
          <p className="finance-guide-note">
            A leitura principal é “Pago”: ela responde quanto saiu do caixa. Os
            demais números ajudam a acompanhar o caminho da despesa.
          </p>
        </section>

        <section className="finance-status-panel" aria-labelledby="finance-status-title">
          <div>
            <span className="eyebrow">Resultado das contas</span>
            <h2 id="finance-status-title">Ainda não classificamos como “no azul” ou “no vermelho”</h2>
            <p>
              Para afirmar déficit ou superávit, precisamos comparar todas as
              receitas e todas as despesas do mesmo período e pelo mesmo critério.
              Hoje temos relatórios de receitas e de pagamentos, mas eles ainda não
              formam um balanço fiscal completo.
            </p>
          </div>
          <span className="finance-status-pill">Resultado fiscal: aguardando base comparável</span>
        </section>

        {monthlyClosures.length > 0 ? (
          <section aria-labelledby="monthly-closure-title" className="monthly-closure-section">
            <div className="section-heading compact">
              <span className="eyebrow">Fechamento do mês</span>
              <h2 id="monthly-closure-title">Uma leitura única das contas</h2>
              <p>
                Cada cartão reúne a receita declarada e os pagamentos do mesmo mês.
                O resultado é calculado por código e só aparece quando as fontes têm
                cobertura comparável.
              </p>
            </div>
            <div className="digest-grid">
              {monthlyClosures.map((closure) => (
                <article className="digest-card monthly-closure-card" key={closure.closureId}>
                  <div className="track-top">
                    <span>{closure.publicBodyName}</span>
                    <span className={`finance-closure-badge finance-closure-${closure.closureStatus}`}>
                      {closureStatusLabel(closure.closureStatus)}
                    </span>
                  </div>
                  <h3 className="procurement-object finance-month-title">
                    {formatMonthTitle(closure.periodEnd)}
                  </h3>
                  <p className="finance-period-note">
                    Competência: {formatDate(closure.periodStart)} a {formatDate(closure.periodEnd)}
                  </p>
                  <div className="monthly-closure-reading">
                    <strong>Comentário do mês</strong>
                    <p>{closure.aiCommentary ?? explainClosure(closure)}</p>
                    {closure.aiCommentary ? (
                      <small className="finance-ai-note">
                        Texto explicativo assistido por IA; os valores e o estado do fechamento
                        são calculados deterministicamente.
                      </small>
                    ) : null}
                  </div>
                  <dl className="procurement-values finance-key-values">
                    <div className="finance-positive-value">
                      <dt>Receita declarada no relatório<small>não é soma das linhas hierárquicas</small></dt>
                      <dd>{closure.revenueReportAmount ? formatBrlDecimal(closure.revenueReportAmount) : "não disponível"}</dd>
                    </div>
                    <div className="finance-negative-value">
                      <dt>Pagamentos efetivados<small>dinheiro que saiu do caixa</small></dt>
                      <dd>{closure.expensePaidAmount ? formatBrlDecimal(closure.expensePaidAmount) : "não disponível"}</dd>
                    </div>
                    <div>
                      <dt>Diferença operacional<small>receita declarada menos pagamentos</small></dt>
                      <dd>{closure.operationalDifferenceAmount ? formatBrlDecimal(closure.operationalDifferenceAmount) : "aguardando reconciliação"}</dd>
                    </div>
                  </dl>
                  <details className="finance-details">
                    <summary>Ver cobertura e memória de cálculo</summary>
                    <p className="finance-details-note">{closure.coverageNote}</p>
                    <dl className="procurement-values">
                      <div><dt>Relatórios de receita usados</dt><dd>{closure.revenueReportCount.toLocaleString("pt-BR")}</dd></div>
                      <div><dt>Linhas de receita preservadas</dt><dd>{closure.revenueLineCount.toLocaleString("pt-BR")}</dd></div>
                      <div><dt>Relatórios de despesa usados</dt><dd>{closure.expenseReportCount.toLocaleString("pt-BR")}</dd></div>
                      {closure.expenseCommittedAmount ? <div><dt>Empenhado no período</dt><dd>{formatBrlDecimal(closure.expenseCommittedAmount)}</dd></div> : null}
                      {closure.expenseLiquidatedAmount ? <div><dt>Liquidado no período</dt><dd>{formatBrlDecimal(closure.expenseLiquidatedAmount)}</dd></div> : null}
                    </dl>
                    <p className="act-evidence">Metodologia determinística: {closure.calculationMethodology}. Receita usa o total declarado por documento; despesas usam o pagamento efetivado do relatório publicado.</p>
                  </details>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {sortedExpenseReports.length > 0 ? (
          <section aria-labelledby="expense-title">
            <div className="section-heading compact">
              <span className="eyebrow">Despesas</span>
              <h2 id="expense-title">Quanto saiu do caixa</h2>
              <p>
                Este é o valor efetivamente pago pela Prefeitura no período do
                relatório. Os meses mais recentes aparecem primeiro.
              </p>
            </div>
            <div className="digest-grid">
              {sortedExpenseReports.map((report) => (
                <article className="digest-card finance-negative-card" key={report.expenseReportId}>
                  <div className="track-top">
                    <span>{report.publicBodyName}</span>
                    <span className="track-status">{report.fiscalYear}</span>
                  </div>
                  <h3 className="procurement-object finance-month-title">
                    {formatMonthTitle(report.periodEnd)}
                  </h3>
                  <p className="finance-period-note">
                    Mês analisado: {formatPeriod(report)} · Prefeitura Municipal de Barreiras
                  </p>
                  <div className="finance-reading finance-reading-card">
                    <strong>Resumo para o cidadão</strong>
                    <p>
                      Entre {formatDate(report.periodStart)} e {formatDate(report.periodEnd)},
                      a Prefeitura pagou {formatBrlDecimal(report.totalPaidPeriodAmount)}.
                      Desde o início do ano, o total pago chegou a {formatBrlDecimal(report.totalPaidToDateAmount)}.
                    </p>
                  </div>
                  <dl className="procurement-values finance-key-values">
                    <div className="revenue-primary-value">
                      <dt>
                        Saiu do caixa no mês
                        <small>pagamento efetivo</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalPaidPeriodAmount)}</dd>
                    </div>
                    <div>
                      <dt>
                        Saiu do caixa no ano
                        <small>pagamento acumulado</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalPaidToDateAmount)}</dd>
                    </div>
                    <div>
                      <dt>
                        Orçamento atualizado
                        <small>limite ajustado, não é gasto</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalUpdatedAmount)}</dd>
                    </div>
                  </dl>
                  <details className="finance-details">
                    <summary>Ver detalhes contábeis deste mês</summary>
                    <dl className="procurement-values">
                      <div>
                        <dt>
                          Entrega conferida
                          <small>liquidado no período</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalLiquidatedPeriodAmount)}</dd>
                      </div>
                      <div>
                        <dt>
                          Valor reservado
                          <small>empenhado no período</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalCommittedPeriodAmount)}</dd>
                      </div>
                      <div>
                        <dt>
                          Saldo informado
                          <small>diferença registrada no relatório</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalBalanceAmount)}</dd>
                      </div>
                    </dl>
                    <p className="finance-details-note">
                      Empenhado, liquidado e pago são etapas diferentes. O site não
                      soma esses valores entre si.
                    </p>
                    <p className="act-evidence">
                      <a href={report.documentSourceUrl} target="_blank" rel="noreferrer">
                        Ver PDF oficial
                      </a>{" "}
                      <a href={report.sourceUrl} target="_blank" rel="noreferrer">
                        Ver resposta da API
                      </a>{" "}
                      · PDF preservado · hash {report.documentArtifactSha256.slice(0, 12)}…
                      · publicado após validação determinística em {formatCollectedAt(report.collectedAt)}
                    </p>
                  </details>
                </article>
              ))}
            </div>
            {expenseLines.length > 0 ? (
              <>
                <details className="finance-details">
                  <summary>Ver os 25 maiores pagamentos do mês</summary>
                  <p className="finance-details-note">
                    Estas são linhas do mesmo mês, ordenadas pelo valor pago. Não
                    são meses diferentes, nem um ranking de empresas ou uma acusação.
                  </p>
                  <div className="digest-grid">
                  {expenseLines.map((line) => (
                    <article className="digest-card finance-negative-card" key={line.expenseLineId}>
                      <div className="track-top">
                        <span>Linha {line.lineNumber.toLocaleString("pt-BR")}</span>
                        <span className="track-status">{line.expenseCode}</span>
                      </div>
                      <h4 className="procurement-object">{line.description}</h4>
                      <dl className="procurement-values">
                        <div className="revenue-primary-value">
                          <dt>Pago no período</dt>
                          <dd>{formatBrlDecimal(line.paidPeriodAmount)}</dd>
                        </div>
                        <div>
                          <dt>Valor atualizado</dt>
                          <dd>{formatBrlDecimal(line.updatedAmount)}</dd>
                        </div>
                        <div>
                          <dt>Empenhado no período</dt>
                          <dd>{formatBrlDecimal(line.committedPeriodAmount)}</dd>
                        </div>
                        <div>
                          <dt>Liquidado no período</dt>
                          <dd>{formatBrlDecimal(line.liquidatedPeriodAmount)}</dd>
                        </div>
                      </dl>
                      <p className="act-evidence">
                        Código-fonte {line.sourceCode} · período {formatDate(line.periodStart)} a {formatDate(line.periodEnd)} ·{" "}
                        <a href={line.documentSourceUrl} target="_blank" rel="noreferrer">
                          abrir documento oficial
                        </a>
                      </p>
                    </article>
                  ))}
                  </div>
                </details>
              </>
            ) : null}
          </section>
        ) : null}

        {sortedRevenues.length > 0 ? (
          <section aria-labelledby="revenue-title">
            <div className="section-heading compact">
              <span className="eyebrow">Dinheiro que entrou</span>
              <h2 id="revenue-title">Receitas da Prefeitura</h2>
              <p>
                O último período disponível é {latestRevenue ? formatDate(latestRevenue) : "não informado"}.
                Os lançamentos completos ficam recolhidos para não misturar meses
                e códigos diferentes.
              </p>
            </div>
            <div className="finance-reading" role="note">
              <strong>Como ler esta parte</strong>
              <p>
                Receita é dinheiro que entrou nos cofres públicos. “No período”
                mostra o intervalo do lançamento; “acumulado” é o total informado
                até aquela data. Não somamos os cartões entre si, porque códigos
                diferentes podem representar partes da mesma conta.
              </p>
            </div>
            <details className="finance-details">
              <summary>Ver lançamentos detalhados de receitas</summary>
              <p className="finance-details-note">
                Cada cartão é uma linha do relatório oficial. Use os links dentro
                dos cartões para abrir o documento e a resposta original.
              </p>
              <div className="digest-grid">
              {sortedRevenues.map((revenue) => (
                  <article
                    className={`digest-card ${
                      revenue.collectionDirection === "deduction"
                        ? "finance-negative-card"
                        : "finance-positive-card"
                    }`}
                    key={revenue.revenueId}
                  >
                  <div className="track-top">
                    <span>{revenue.publicBodyName}</span>
                    <span className="track-status">{revenue.fiscalYear}</span>
                  </div>
                  <h3 className="procurement-object">{revenue.description}</h3>
                  <dl className="procurement-values">
                    <div className="revenue-primary-value">
                      <dt>
                        {revenue.collectionDirection === "deduction"
                          ? "Deduções no período"
                          : "Valor arrecadado no período"}
                      </dt>
                      <dd>{formatBrlDecimal(revenue.collectedAmount)}</dd>
                    </div>
                    <div>
                      <dt>Acumulado no relatório</dt>
                      <dd>{formatBrlDecimal(revenue.accumulatedAmount)}</dd>
                    </div>
                    <div>
                      <dt>Total declarado no relatório</dt>
                      <dd>{formatBrlDecimal(revenue.reportTotalPeriodAmount)}</dd>
                    </div>
                    <div>
                      <dt>Data da receita</dt>
                      <dd>{formatDate(revenue.revenueDate)}</dd>
                    </div>
                    {revenue.revenueCode ? (
                      <div>
                        <dt>Código</dt>
                        <dd>{revenue.revenueCode}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <div className="finance-reading finance-reading-card">
                    <strong>Leitura rápida</strong>
                    <p>{explainRevenue(revenue)}</p>
                  </div>
                  <p className="act-evidence">
                    {revenue.documentSourceUrl ? (
                      <a
                        href={revenue.documentSourceUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Ver PDF oficial
                      </a>
                    ) : null}{" "}
                    {revenue.sourceUrl ? (
                      <a href={revenue.sourceUrl} target="_blank" rel="noreferrer">
                        Ver resposta da API
                      </a>
                    ) : null}{" "}
                    · PDF preservado · hash {revenue.documentArtifactSha256.slice(0, 12)}…
                    · publicado após validação determinística em {formatCollectedAt(revenue.collectedAt)}
                  </p>
                </article>
              ))}
              </div>
            </details>
          </section>
        ) : null}

        <section aria-labelledby="document-title" className="finance-documents">
          <div className="section-heading compact">
            <span className="eyebrow">Documentos oficiais</span>
            <h2 id="document-title">O que a Prefeitura publicou</h2>
            <p>
              {sortedDocuments.length > 0
                ? `Exibindo ${sortedDocuments.length.toLocaleString("pt-BR")} documentos financeiros, do mais recente ao mais antigo. O histórico completo será paginado por período.`
                : "A coleta dos documentos financeiros ainda não está disponível."}
            </p>
          </div>

          {documents.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Nenhum documento financeiro preservado ainda</strong>
                <p>
                  Isso não significa receita zero. A API oficial publica parte
                  das informações como PDFs; o coletor precisa preservar o
                  documento antes de extrair números.
                </p>
                <a
                  href="https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Consultar a fonte oficial →
                </a>
              </div>
            </div>
          ) : (
            <div className="digest-grid">
              {sortedDocuments.map((document) => (
                <article className="digest-card" key={document.documentId}>
                  <div className="track-top">
                    <span>{financeResourceLabel(document.sourceResource)}</span>
                    <span className="track-status">
                      {document.fiscalYear ?? "período não informado"}
                    </span>
                  </div>
                  <h3 className="procurement-object">{document.title}</h3>
                  <dl className="procurement-values">
                    <div>
                      <dt>Referência</dt>
                      <dd>{document.referenceDate ?? "não informada"}</dd>
                    </div>
                    {document.description ? (
                      <div>
                        <dt>Descrição</dt>
                        <dd>{document.description}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <p className="act-evidence">
                    <a href={document.documentUrl} target="_blank" rel="noreferrer">
                      Abrir documento oficial →
                    </a>{" "}
                    · resposta da API preservada · {document.documentPreserved
                      ? "PDF preservado"
                      : "PDF ainda não preservado"}{" "}
                    · hash {document.artifactSha256.slice(0, 12)}…
                  </p>
                </article>
              ))}
            </div>
          )}
        </section>

        <p className="hero-note">
          Metodologia: empenho, liquidação, pagamento e receita são estágios
          diferentes. O Barreiras 360 não soma esses estágios como se fossem a
          mesma coisa. Deduções são exibidas com sinal negativo e só aparecem
          quando o PDF, o período, o hash e a estrutura do relatório passam por
          validação determinística.
        </p>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="/">
              <span>Barreiras 360</span>
            </a>
            <p>Informação pública de Barreiras para acompanhar a cidade com clareza.</p>
          </div>
          <div className="footer-status">
            <span className="status-dot" />
            Receitas e documentos somente com fonte e evidência
          </div>
        </div>
      </footer>
    </main>
  );
}
