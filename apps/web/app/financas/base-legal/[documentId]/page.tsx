import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getMunicipalControlDocument } from "../../../../lib/municipal-control-documents";

export const revalidate = 300;

type PageProps = Readonly<{
  params: Promise<{ documentId: string }>;
}>;

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { documentId } = await params;
  const result = await getMunicipalControlDocument(documentId);
  if (result.state !== "available") return { title: "Documento da base legal" };
  return {
    title: `${result.document.title} | Base legal municipal`,
    description: "Texto integral preservado de documento oficial do Município de Barreiras.",
  };
}

export default async function MunicipalControlDocumentPage({ params }: PageProps) {
  const { documentId } = await params;
  const result = await getMunicipalControlDocument(documentId);
  if (result.state === "not_found") notFound();

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/financas/base-legal" aria-label="Voltar para a base legal">
            <span>← Base legal</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/financas">Finanças</a>
            <a href="/sobre">Como verificamos</a>
          </nav>
        </div>
      </header>

      <section className="section legal-document-page" aria-labelledby="legal-document-title">
        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Documento temporariamente indisponível</strong>
              <p>A falha é de consulta; tente novamente em instantes.</p>
            </div>
          </div>
        ) : (
          <article>
            <div className="section-heading">
              <span className="eyebrow">Texto oficial, sem resumo</span>
              <h1 id="legal-document-title">{result.document.title}</h1>
              <p>
                Texto integral preservado do arquivo oficial. A formatação visual
                foi simplificada para leitura, mas as palavras não foram reescritas.
              </p>
            </div>
            <dl className="legal-document-metadata">
              <div>
                <dt>Data informada pela fonte</dt>
                <dd>{result.document.referenceDate ?? "não informada"}</dd>
              </div>
              <div>
                <dt>Arquivo oficial</dt>
                <dd>
                  <a href={result.document.documentSourceUrl} target="_blank" rel="noreferrer">
                    Abrir documento oficial ↗
                  </a>
                </dd>
              </div>
              <div>
                <dt>SHA-256 do arquivo</dt>
                <dd><code>{result.document.documentArtifactSha256}</code></dd>
              </div>
              <div>
                <dt>SHA-256 do texto</dt>
                <dd><code>{result.document.textSha256}</code></dd>
              </div>
            </dl>
            {result.document.description ? <p>{result.document.description}</p> : null}
            <div className="legal-text-reader" aria-label="Texto integral do documento">
              {result.document.fullText}
            </div>
            <p className="hero-note">
              Este texto pertence à base legal de controle. Ele não é um
              demonstrativo financeiro e não comprova, isoladamente, valores
              arrecadados, empenhados ou pagos.
            </p>
          </article>
        )}
      </section>
    </main>
  );
}
