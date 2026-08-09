import type { Metadata } from "next";

import { getQueridoDiarioCollectionStatus } from "../../lib/collection-status";
import {
  enrichIntegralGazetteEditions,
  getIntegralGazetteEditions,
} from "../../lib/integral-gazette-documents";
import {
  getOfficialDiaryCatalog,
  type OfficialDiaryCatalogEntry,
} from "../../lib/official-diary-catalog";
import { IntegralGazetteExplorer } from "./integral-gazette-explorer";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Diário Oficial organizado",
  description:
    "Texto integral do Diário Oficial de Barreiras, separado por edição e documento, com fonte e hash verificáveis.",
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

function CatalogPendingNotice({
  entries,
}: Readonly<{ entries: readonly OfficialDiaryCatalogEntry[] }>) {
  if (entries.length === 0) return null;
  return (
    <div className="collection-unavailable" role="status">
      <div>
        <strong>
          {entries.length} edição{entries.length === 1 ? "" : "ões"} aguardando
          preservação integral
        </strong>
        <p>
          O catálogo oficial já registrou estas edições. Elas aparecerão aqui
          quando o arquivo integral for preservado e conferido, sem alterar o
          texto da fonte.
        </p>
      </div>
    </div>
  );
}

export default async function IntegralDiaryPage() {
  const [integralResult, catalogResult, collectionStatus] = await Promise.all([
    getIntegralGazetteEditions(),
    getOfficialDiaryCatalog(),
    getQueridoDiarioCollectionStatus(),
  ]);
  const catalogEntries =
    catalogResult.state === "available" ? catalogResult.entries : [];
  const editions =
    integralResult.state === "available"
      ? enrichIntegralGazetteEditions(integralResult.editions, catalogEntries)
      : [];
  const latestCatalogCollectedAt = catalogEntries
    .map((entry) => entry.collectedAt)
    .sort()
    .at(-1);

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/atos">Atos públicos</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="integral-diary-title">
        <div className="section-heading">
          <span className="eyebrow">Fonte oficial, texto completo</span>
          <h1 id="integral-diary-title">Diário Oficial organizado</h1>
          <p>
            O conteúdo abaixo é a transcrição integral dos arquivos
            preservados. Apenas agrupamos as páginas em documentos quando a
            separação é segura; em caso de dúvida, mantemos a edição inteira.
            O texto não é reescrito.
          </p>
          {latestCatalogCollectedAt ? (
            <p className="source-freshness" role="status">
              <span className="status-dot" aria-hidden="true" />
              Catálogo oficial preservado em{" "}
              {dateTimeFormatter.format(new Date(latestCatalogCollectedAt))}
              {" "}· atualização automática ativa
            </p>
          ) : null}
          {collectionStatus.state === "available" ? (
            <details className="digest-official-source">
              <summary>Ver estado da coleta automática</summary>
              <p>
                A API do Querido Diário foi consultada pela última vez em{" "}
                {dateTimeFormatter.format(
                  new Date(collectionStatus.data.lastSuccessfulAt),
                )}
                . O acervo preserva{" "}
                {collectionStatus.data.preservedEditionCount} edições
                distintas. A coleta direta do catálogo oficial roda em
                paralelo.
              </p>
            </details>
          ) : null}
        </div>

        {editions.length === 0 && catalogEntries.length > 0 ? (
          <CatalogPendingNotice entries={catalogEntries} />
        ) : editions.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhuma edição integral disponível</strong>
              <p>
                A coleta preservará o arquivo oficial antes de exibir qualquer
                conteúdo nesta página.
              </p>
            </div>
          </div>
        ) : (
          <IntegralGazetteExplorer editions={editions} />
        )}

        <p className="hero-note">
          Cada documento mantém o texto original, a edição, as páginas, a
          origem e o hash SHA-256 do artefato preservado. Encontrou um erro?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/diario&labels=correcao"
            target="_blank"
            rel="noreferrer"
          >
            Abra um pedido público de correção
          </a>
          .
        </p>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="/">
              <span>Barreiras 360</span>
            </a>
            <p>
              Informação pública de Barreiras para acompanhar a cidade com
              clareza.
            </p>
          </div>
          <div className="footer-status">
            <span className="status-dot" />
            Texto integral ancorado no documento oficial
          </div>
        </div>
      </footer>
    </main>
  );
}
