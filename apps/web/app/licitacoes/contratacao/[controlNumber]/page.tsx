import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getPncpProcurement } from "../../../../lib/pncp-procurements";
import ShareLink from "../../../share-link";
import { ProcurementCard, procurementDetailPath } from "../../procurement-explorer";

export const revalidate = 300;

type ProcurementPageProps = Readonly<{
  params: Promise<{ controlNumber: string }>;
}>;

export async function generateMetadata({
  params,
}: ProcurementPageProps): Promise<Metadata> {
  const { controlNumber } = await params;
  const decoded = decodeURIComponent(controlNumber);
  return {
    title: `Contratação ${decoded}`,
    description:
      "Contratação pública de Barreiras no PNCP: itens, quem venceu, " +
      "execução ligada por identificador oficial e evidências preservadas.",
    alternates: { canonical: procurementDetailPath(decoded) },
  };
}

export default async function ProcurementDetailPage({
  params,
}: ProcurementPageProps) {
  const { controlNumber } = await params;
  const decoded = decodeURIComponent(controlNumber);
  const result = await getPncpProcurement(decoded);
  if (result.state === "available" && result.procurement === null) notFound();

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/licitacoes">← Licitações</a>
      </nav>

      <section className="section" aria-labelledby="procurement-detail-title">
        <div className="section-heading">
          <span className="eyebrow">Contratação no PNCP</span>
          <h1 id="procurement-detail-title">Processo {decoded}</h1>
          <p>
            Registro oficial do Portal Nacional de Contratações Públicas com
            itens, resultados homologados e a execução financeira ligada por
            identificador oficial. Nada aqui é avaliação de legalidade.
          </p>
          <ShareLink
            path={procurementDetailPath(decoded)}
            message={`Contratação ${decoded} da Prefeitura de Barreiras, com itens e quem venceu:`}
          />
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Contratação temporariamente indisponível</strong>
              <p>
                Isso representa uma falha de consulta, não a inexistência da
                contratação. Tente novamente em instantes ou volte à{" "}
                <a href="/licitacoes">lista de licitações</a>.
              </p>
            </div>
          </div>
        ) : result.procurement ? (
          <ProcurementCard procurement={result.procurement} />
        ) : null}
      </section>
    </main>
  );
}
