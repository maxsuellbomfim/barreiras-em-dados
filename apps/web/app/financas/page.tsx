import type { Metadata } from "next";

import {
  formatBrlDecimal,
  getPublicRevenues,
} from "../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Finanças públicas",
  description:
    "Receitas municipais normalizadas com fonte, data de coleta e evidência verificável.",
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  return value
    ? dateFormatter.format(new Date(`${value}T12:00:00-03:00`))
    : "data não informada";
}

export default async function FinancesPage() {
  const result = await getPublicRevenues();

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
          <span className="eyebrow">Receitas do município</span>
          <h1 id="finances-title">Finanças públicas, sem esconder a conta.</h1>
          <p>
            Esta página exibirá receitas normalizadas a partir dos registros
            oficiais da Prefeitura. Cada linha terá sua fonte, data e artefato
            preservado. Totais só aparecem quando forem calculados por código
            sobre dados reconciliados.
          </p>
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Dados financeiros temporariamente indisponíveis</strong>
              <p>
                A base ainda está sendo validada. Isso não significa receita
                zero nem ausência de publicação na fonte oficial.
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
        ) : result.revenues.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhuma receita reconciliada foi publicada ainda</strong>
              <p>
                A coleta bruta e o contrato de normalização já estão preparados;
                a publicação aguarda confirmação de classificação, estornos e
                chaves estáveis.
              </p>
            </div>
          </div>
        ) : (
          <>
            <p className="acts-count" role="status">
              {result.revenues.length.toLocaleString("pt-BR")} registros de receita
            </p>
            <div className="digest-grid">
              {result.revenues.map((revenue) => (
                <article className="digest-card" key={revenue.revenueId}>
                  <div className="track-top">
                    <span>{revenue.publicBodyName}</span>
                    <span className="track-status">
                      {revenue.fiscalYear}
                    </span>
                  </div>
                  <h2 className="procurement-object">{revenue.description}</h2>
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
                    {dateFormatter.format(new Date(revenue.collectedAt))}
                  </p>
                </article>
              ))}
            </div>
          </>
        )}

        <p className="hero-note">
          Metodologia: valores monetários são tratados como decimal exato. Esta
          página não soma empenho, liquidação, pagamento e receita como se fossem
          o mesmo estágio contábil.
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
            Receitas somente com fonte e evidência
          </div>
        </div>
      </footer>
    </main>
  );
}

