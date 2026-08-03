import type { Metadata } from "next";

import {
  financeResourceLabel,
  getPublicFinanceDocuments,
} from "../../lib/finance-documents";
import {
  formatBrlDecimal,
  getPublicRevenues,
  type PublicRevenue,
} from "../../lib/revenues";

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

function sortNewest<T extends { revenueDate?: string | null; referenceDate?: string | null; collectedAt: string }>(
  rows: readonly T[],
  dateKey: "revenueDate" | "referenceDate",
): T[] {
  return [...rows].sort((left, right) => {
    const leftDate = left[dateKey] ?? left.collectedAt;
    const rightDate = right[dateKey] ?? right.collectedAt;
    return rightDate.localeCompare(leftDate);
  });
}

function explainRevenue(revenue: PublicRevenue): string {
  if (revenue.collectionDirection === "deduction") {
    return `Este registro é uma dedução de ${formatBrlDecimal(revenue.collectedAmount)} no período. Ela aparece com sinal negativo para não ser confundida com arrecadação bruta.`;
  }
  return `Este registro representa ${formatBrlDecimal(revenue.collectedAmount)} arrecadados no período. O acumulado informado no relatório é ${formatBrlDecimal(revenue.accumulatedAmount)}.`;
}

export default async function FinancesPage() {
  const [revenuesResult, documentsResult] = await Promise.all([
    getPublicRevenues(),
    getPublicFinanceDocuments(),
  ]);
  const revenues =
    revenuesResult.state === "available" ? revenuesResult.revenues : [];
  const documents =
    documentsResult.state === "available" ? documentsResult.documents : [];
  const sortedRevenues = sortNewest(revenues, "revenueDate");
  const sortedDocuments = sortNewest(documents, "referenceDate");
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

        {sortedRevenues.length > 0 ? (
          <section aria-labelledby="revenue-title">
            <div className="finance-overview" aria-label="Resumo das finanças">
              <div className="finance-overview-card finance-overview-card-primary">
                <span>Registros exibidos</span>
                <strong>{sortedRevenues.length.toLocaleString("pt-BR")}</strong>
                <small>de receitas validadas · até 200 por consulta</small>
              </div>
              <div className="finance-overview-card">
                <span>Registro mais recente</span>
                <strong>{latestRevenue ? formatDate(latestRevenue) : "—"}</strong>
                <small>ordenado do mais novo para o mais antigo</small>
              </div>
              <div className="finance-overview-card">
                <span>Documentos exibidos</span>
                <strong>{documents.length.toLocaleString("pt-BR")}</strong>
                <small>preservados · até 200 por consulta</small>
              </div>
            </div>
            <div className="section-heading compact">
              <span className="eyebrow">Dados numéricos validados</span>
              <h2 id="revenue-title">Receitas normalizadas</h2>
            <p>
              Exibindo {sortedRevenues.length.toLocaleString("pt-BR")} registros
                com cálculo determinístico, versão e evidência de origem. A
                publicação é automática quando todos os checks passam; o histórico
                completo será paginado por período.
            </p>
            </div>
            <div className="finance-reading" role="note">
              <strong>Como ler estes valores</strong>
              <p>
                Cada cartão representa um código de receita no relatório. “No período”
                é o valor daquele intervalo; “acumulado” é o acumulado informado no
                próprio documento. Não somamos os cartões entre si, porque códigos e
                estágios diferentes podem representar partes da mesma conta.
              </p>
            </div>
            <div className="digest-grid">
              {sortedRevenues.map((revenue) => (
                <article className="digest-card" key={revenue.revenueId}>
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
