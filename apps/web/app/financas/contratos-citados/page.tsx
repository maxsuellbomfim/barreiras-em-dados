import type { Metadata } from "next";

import {
  FIRST_CITATION_YEAR,
  citationYear,
  getPublicContractCitations,
  type ContractCitationGroup,
} from "../../../lib/contract-citations.mjs";
import { formatBrlDecimal } from "../../../lib/revenues";

export const revalidate = 300;

// ponytail: fora do índice e sem link até a conferência registrada (ADR 0096);
// ao publicar, tirar o robots e ligar em /financas e no sitemap.
export const metadata: Metadata = {
  title: "Citações de contrato em empenhos | Finanças",
  description:
    "Comparação entre os contratos citados nos empenhos da Prefeitura de Barreiras e a lista de contratos publicada no Portal da Transparência.",
  robots: { index: false, follow: false },
};

type PageProps = Readonly<{ searchParams: Promise<{ ano?: string }> }>;

const CORRECTION_URL =
  "https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/financas/contratos-citados&labels=correcao";

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function CitationTable({
  caption,
  groups,
}: Readonly<{ caption: string; groups: readonly ContractCitationGroup[] }>) {
  return (
    <div className="territorial-table-wrap" role="region" aria-label={caption} tabIndex={0}>
      <table className="territorial-table recipients-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Órgão e credor</th>
            <th scope="col">Contrato citado</th>
            <th scope="col">Pago</th>
            <th scope="col">Empenhos</th>
            <th scope="col">Período dos empenhos</th>
            <th scope="col">Situação</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr
              key={`${group.publicBody}|${group.creditorName ?? "pf"}|${group.citedNumber ?? ""}`}
            >
              <th scope="row">
                {group.creditorName ??
                  "Pessoas físicas (nomes, números e trechos não publicados)"}
                <span className="meta"> · {group.publicBody}</span>
              </th>
              <td>
                {group.citedNumber ?? "—"}
                {group.citedExcerpt ? <span className="meta"> · “{group.citedExcerpt}”</span> : null}
              </td>
              <td className="territorial-table-number">
                {formatBrlDecimal(group.paidAmount)}
                {group.unreadablePayments > 0 ? (
                  <span className="meta">
                    {" "}
                    · {group.unreadablePayments} pagamento(s) com valor ilegível fora da soma
                  </span>
                ) : null}
              </td>
              <td className="territorial-table-number">
                {group.commitments.toLocaleString("pt-BR")}
              </td>
              <td>
                {formatDate(group.firstIssueDate)} a {formatDate(group.lastIssueDate)}
                {group.latestCommitmentKey ? (
                  <span className="meta"> · último {group.latestCommitmentKey}</span>
                ) : null}
              </td>
              <td>
                {group.category === "publicado_no_pncp" ? (
                  <>
                    Publicado no PNCP (mesmo número; fornecedor conferido pelo nome)
                    {group.pncpUrl ? (
                      <>
                        {" "}
                        <a href={group.pncpUrl} target="_blank" rel="noreferrer">
                          ver no PNCP
                        </a>
                      </>
                    ) : null}
                  </>
                ) : (
                  <>
                    Número citado sem correspondência exata na lista lida em{" "}
                    {formatDate(group.listReadOn)} (regra contract-citation-comparison/1.0.0)
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function ContractCitationsPage({ searchParams }: PageProps) {
  const currentYear = new Date().getFullYear();
  const year = citationYear((await searchParams).ano, currentYear);
  const result = await getPublicContractCitations(year);
  const years = Array.from(
    { length: currentYear - FIRST_CITATION_YEAR + 1 },
    (_, index) => currentYear - index,
  );

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/financas">← Finanças</a>
      </nav>

      <section className="section" aria-labelledby="contract-citations-title">
        <div className="section-heading">
          <span className="eyebrow">Rastro do dinheiro</span>
          <h1 id="contract-citations-title">
            Citações de contrato em empenhos: comparação com a lista de contratos do portal
          </h1>
          <p>
            O histórico de muitos empenhos cita o contrato que os sustenta. Esta página mostra os
            números citados que não têm correspondência exata na lista de contratos publicada no
            Portal da Transparência. <strong>Não indica irregularidade</strong>: o contrato pode
            ter sido publicado com outro número, em outro portal, como aditivo, ata, convênio ou
            credenciamento, ou ainda não ter sido publicado.
          </p>
        </div>

        <nav className="rentals-years" aria-label="Ano dos empenhos">
          {years.map((option) => (
            <a
              key={option}
              href={`/financas/contratos-citados?ano=${option}`}
              aria-current={option === year ? "page" : undefined}
            >
              {option}
            </a>
          ))}
        </nav>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Comparação temporariamente indisponível</strong>
              <p>A falha é de consulta; ela não significa que não haja citações.</p>
            </div>
          </div>
        ) : result.state === "awaiting_review" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Aguardando conferência humana</strong>
              <p>
                A comparação já é calculada, mas só será exibida depois que um revisor conferir
                no portal uma amostra registrada de casos e aprovar esta versão da regra.
              </p>
            </div>
          </div>
        ) : (
          <>
            <CitationTable
              caption={`Sem correspondência exata na lista do portal — empenhos de ${year}`}
              groups={result.groups.filter((group) => group.category === "sem_correspondencia")}
            />
            <CitationTable
              caption={`Publicados no PNCP com o mesmo número — empenhos de ${year}`}
              groups={result.groups.filter((group) => group.category === "publicado_no_pncp")}
            />
            <p className="hero-note">
              Conferência humana registrada em {formatDate(result.approvedAt.slice(0, 10))}.
              Fonte dos empenhos e pagamentos:{" "}
              <a href={result.groups[0]?.sourcePageUrl} target="_blank" rel="noreferrer">
                Portal da Transparência
              </a>
              .
            </p>
          </>
        )}

        <p className="hero-note">
          Metodologia contract-citation-comparison/1.0.0 (ADR 0096): vale a decisão mais recente
          de cada empenho orçamentário. O valor é só o <strong>pago</strong> — soma exata das
          ordens de pagamento ligadas ao empenho pela chave oficial; o empenhado não é somado
          porque o portal não publica anulações. A Câmara fica de fora: publica contratos em
          portal próprio. Credores pessoa física (inclusive MEI com nome de pessoa) aparecem só
          somados por órgão. A ordem é por órgão e data, não por valor.
        </p>
        <p className="hero-note">
          Falsos positivos conhecidos: sufixo de órgão escrito de outro jeito, erro de digitação
          no histórico, aditivo ou apostila citado como contrato, ata de registro de preços,
          convênio, credenciamento SUS ou consórcio, contrato de outro ente, contrato encerrado
          retirado da lista e defasagem entre o empenho e a leitura da lista. A Prefeitura e os
          fornecedores podem{" "}
          <a href={CORRECTION_URL} target="_blank" rel="noreferrer">
            pedir correção ou registrar resposta
          </a>
          .
        </p>
      </section>
    </main>
  );
}
