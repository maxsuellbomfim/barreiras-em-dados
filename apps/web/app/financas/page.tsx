import type { Metadata } from "next";

import {
  financeResourceLabel,
  getPublicFinanceDocuments,
} from "../../lib/finance-documents";
import { formatBrlDecimal, getPublicRevenues } from "../../lib/revenues";

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

export default async function FinancesPage() {
  const [revenuesResult, documentsResult] = await Promise.all([
    getPublicRevenues(),
    getPublicFinanceDocuments(),
  ]);
  const revenues =
    revenuesResult.state === "available" ? revenuesResult.revenues : [];
  const documents =
    documentsResult.state === "available" ? documentsResult.documents : [];

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

        {revenues.length > 0 ? (
          <section aria-labelledby="revenue-title">
            <div className="section-heading compact">
              <span className="eyebrow">Dados numéricos validados</span>
              <h2 id="revenue-title">Receitas normalizadas</h2>
              <p>
                {revenues.length.toLocaleString("pt-BR")} registros com cálculo
                determinístico, versão e evidência de origem.
              </p>
            </div>
            <div className="digest-grid">
              {revenues.map((revenue) => (
                <article className="digest-card" key={revenue.revenueId}>
                  <div className="track-top">
                    <span>{revenue.publicBodyName}</span>
                    <span className="track-status">{revenue.fiscalYear}</span>
                  </div>
                  <h3 className="procurement-object">{revenue.description}</h3>
                  <dl className="procurement-values">
                    <div>
                      <dt>Valor arrecadado</dt>
                      <dd>{formatBrlDecimal(revenue.collectedAmount)}</dd>
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
                  <p className="act-evidence">
                    {revenue.sourceUrl ? (
                      <a href={revenue.sourceUrl} target="_blank" rel="noreferrer">
                        Ver fonte preservada
                      </a>
                    ) : (
                      <span>Fonte preservada sem URL pública</span>
                    )}{" "}
                    · hash {revenue.artifactSha256.slice(0, 12)}… · coletado em{" "}
                    {formatCollectedAt(revenue.collectedAt)}
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
              {documents.length > 0
                ? `${documents.length.toLocaleString("pt-BR")} documentos financeiros encontrados.`
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
              {documents.map((document) => (
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
          mesma coisa e não publica valor extraído de PDF sem validação.
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
