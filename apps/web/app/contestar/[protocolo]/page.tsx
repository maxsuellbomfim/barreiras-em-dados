import type { Metadata } from "next";

import {
  STATUS_LABELS,
  getContestation,
  normalizeProtocol,
} from "../../../lib/contestations.mjs";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Andamento da contestação",
  robots: { index: false },
};

type PageProps = Readonly<{ params: Promise<{ protocolo: string }> }>;

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Bahia" });
}

export default async function ContestationStatusPage({ params }: PageProps) {
  const protocol = normalizeProtocol((await params).protocolo);
  const result = protocol ? await getContestation(protocol) : ({ state: "not_found" } as const);

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/contestar">← Contestar</a>
      </nav>
      <section className="section" aria-labelledby="contest-status-title">
        <div className="section-heading">
          <span className="eyebrow">Correção e direito de resposta</span>
          <h1 id="contest-status-title">Andamento da contestação</h1>
        </div>
        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Consulta temporariamente indisponível</strong>
              <p>Tente de novo em alguns minutos. O protocolo continua válido.</p>
            </div>
          </div>
        ) : result.state === "not_found" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Protocolo não encontrado</strong>
              <p>Confira o código: ele começa com C- seguido de 10 letras e números.</p>
            </div>
          </div>
        ) : (
          <article className="digest-card">
            <p>
              Protocolo <strong>{result.protocol}</strong> — guarde este código para acompanhar.
            </p>
            <dl className="finance-details-list">
              <div>
                <dt>Página contestada</dt>
                <dd>
                  <a href={result.targetPath}>{result.targetPath}</a>
                </dd>
              </div>
              <div>
                <dt>Recebida em</dt>
                <dd>{formatDateTime(result.createdAt)}</dd>
              </div>
              <div>
                <dt>Andamento</dt>
                <dd>{STATUS_LABELS[result.status]}</dd>
              </div>
              {result.resolutionNote ? (
                <div>
                  <dt>Resolução{result.resolvedAt ? ` (${formatDateTime(result.resolvedAt)})` : ""}</dt>
                  <dd>{result.resolutionNote}</dd>
                </div>
              ) : null}
            </dl>
          </article>
        )}
      </section>
    </main>
  );
}
