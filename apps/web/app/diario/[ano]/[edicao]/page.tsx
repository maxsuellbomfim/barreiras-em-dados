import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  enrichIntegralGazetteEditions,
  getIntegralGazetteEdition,
} from "../../../../lib/integral-gazette-documents";
import { getOfficialDiaryCatalog } from "../../../../lib/official-diary-catalog";
import ShareLink from "../../../share-link";
import { IntegralGazetteExplorer } from "../../integral-gazette-explorer";

export const revalidate = 300;

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

type EditionPageParams = Readonly<{
  params: Promise<{ ano: string; edicao: string }>;
}>;

function parsedParams(ano: string, edicao: string) {
  const editionYear = Number.parseInt(ano, 10);
  const edition = Number.parseInt(edicao, 10);
  if (
    !Number.isSafeInteger(editionYear) ||
    editionYear < 2000 ||
    editionYear > 2100 ||
    !Number.isSafeInteger(edition) ||
    edition < 1 ||
    String(editionYear) !== ano.trim() ||
    String(edition) !== edicao.trim()
  ) {
    return null;
  }
  return { editionYear, edition };
}

export async function generateMetadata({
  params,
}: EditionPageParams): Promise<Metadata> {
  const { ano, edicao } = await params;
  const parsed = parsedParams(ano, edicao);
  if (!parsed) return { title: "Edição não encontrada" };
  const title = `Diário Oficial — edição ${parsed.edition}/${parsed.editionYear}`;
  return {
    title,
    description:
      "Texto integral da edição do Diário Oficial de Barreiras, separado " +
      "por documento, com fonte e hash verificáveis.",
    alternates: {
      canonical: `/diario/${parsed.editionYear}/${parsed.edition}`,
    },
    openGraph: {
      title,
      description:
        "Texto integral da edição, separado por documento, com fonte e " +
        "hash verificáveis.",
    },
  };
}

export default async function GazetteEditionPage({ params }: EditionPageParams) {
  const { ano, edicao } = await params;
  const parsed = parsedParams(ano, edicao);
  if (!parsed) notFound();
  const [result, catalogResult] = await Promise.all([
    getIntegralGazetteEdition(parsed.editionYear, parsed.edition),
    getOfficialDiaryCatalog(),
  ]);
  if (result.state === "available" && result.edition === null) notFound();
  const editions =
    result.state === "available" && result.edition
      ? enrichIntegralGazetteEditions(
          [result.edition],
          catalogResult.state === "available" ? catalogResult.entries : [],
        )
      : [];
  const edition = editions[0] ?? null;
  const editionDate = edition?.editionDate ?? edition?.catalogDate ?? null;
  const path = `/diario/${parsed.editionYear}/${parsed.edition}`;

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/diario" aria-label="Diário Oficial organizado">
            <span>← Diário Oficial</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/atos">Atos públicos</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="edition-title">
        <div className="section-heading">
          <span className="eyebrow">Fonte oficial, texto completo</span>
          <h1 id="edition-title">
            Diário Oficial — edição {parsed.edition}/{parsed.editionYear}
          </h1>
          <p>
            {editionDate
              ? `Edição publicada em ${dateFormatter.format(
                  new Date(`${editionDate}T12:00:00-03:00`),
                )}. `
              : ""}
            Transcrição integral do arquivo preservado, separada por
            documento quando a separação é segura. O texto não é reescrito e
            cada documento carrega o hash do conteúdo.
          </p>
          <ShareLink
            path={path}
            message={`Diário Oficial de Barreiras, edição ${parsed.edition}/${parsed.editionYear}, na íntegra e pesquisável:`}
          />
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Edição temporariamente indisponível</strong>
              <p>
                Isso representa uma falha de consulta, não a inexistência da
                edição. Tente novamente em instantes ou volte ao{" "}
                <a href="/diario">acervo completo</a>.
              </p>
            </div>
          </div>
        ) : edition ? (
          <IntegralGazetteExplorer editions={[edition]} />
        ) : null}

        <p className="hero-note">
          Endereço permanente desta edição para citação e compartilhamento.
          Encontrou um erro?{" "}
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
