import type { Metadata } from "next";

import { formatBrlCompact } from "../../../lib/compact-money.mjs";
import {
  FIRST_RENTAL_YEAR,
  getPublicPropertyRentals,
  rentalYear,
} from "../../../lib/property-rentals.mjs";
import { formatBrlDecimal } from "../../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Aluguéis de imóveis | Finanças",
  description:
    "Imóveis alugados pela Prefeitura de Barreiras: locador, uso do imóvel, contrato, valor empenhado e valor pago, com a fonte oficial de cada empenho.",
};

type PageProps = Readonly<{ searchParams: Promise<{ ano?: string }> }>;

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

export default async function PropertyRentalsPage({ searchParams }: PageProps) {
  const currentYear = new Date().getFullYear();
  const year = rentalYear((await searchParams).ano, currentYear);
  const result = await getPublicPropertyRentals(year);
  const years = Array.from(
    { length: currentYear - FIRST_RENTAL_YEAR + 1 },
    (_, index) => currentYear - index,
  );

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/financas">← Finanças</a>
      </nav>

      <section className="section" aria-labelledby="rentals-title">
        <div className="section-heading">
          <span className="eyebrow">Classificação oficial do empenho</span>
          <h1 id="rentals-title">Aluguéis de imóveis da Prefeitura</h1>
          <p>
            Empenhos que a própria Prefeitura classifica como <strong>locação de imóveis</strong>,
            agrupados por locador e contrato. A descrição é o texto do empenho mais recente,
            como publicado no Portal da Transparência: ali estão o endereço e o uso do imóvel.
          </p>
        </div>

        <nav className="rentals-years" aria-label="Ano dos empenhos">
          {years.map((option) => (
            <a
              key={option}
              href={`/financas/alugueis?ano=${option}`}
              aria-current={option === year ? "page" : undefined}
            >
              {option}
            </a>
          ))}
        </nav>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Aluguéis temporariamente indisponíveis</strong>
              <p>A falha é de consulta; ela não significa que não haja aluguéis.</p>
            </div>
          </div>
        ) : result.rentals.length === 0 || result.summary === null ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhum empenho de locação de imóvel em {year}</strong>
              <p>Nenhum empenho coletado deste ano tem essa classificação.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="glance-grid">
              <article className="glance-card">
                <span className="glance-question">Locadores</span>
                <span className="glance-value">{result.summary.landlords}</span>
                <span className="glance-context">
                  {result.summary.commitments.toLocaleString("pt-BR")} empenhos em {year}
                  {result.summary.addresses !== null
                    ? ` · ${result.summary.addresses} endereços distintos citados`
                    : ""}
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Empenhado</span>
                <span className="glance-value">
                  {formatBrlCompact(result.summary.committedAmount)}
                </span>
                <span className="glance-exact">
                  {formatBrlDecimal(result.summary.committedAmount)}
                </span>
                <span className="glance-context">Valor reservado no orçamento, bruto.</span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Pago aos locadores</span>
                <span className="glance-value">
                  {formatBrlCompact(result.summary.paidAmount)}
                </span>
                <span className="glance-exact">{formatBrlDecimal(result.summary.paidAmount)}</span>
                <span className="glance-context">
                  Pagamentos ligados a estes empenhos pela chave oficial, até a última coleta.
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Meses coletados</span>
                <span className="glance-value">{result.summary.gridMonths} de 12</span>
                <span className="glance-context">
                  Meses de {year} cuja grade de empenhos foi preservada.
                </span>
              </article>
            </div>

            <p className="hero-note">
              O pago pode ser menor que o empenhado: empenho por estimativa pode ser anulado ou
              não usado por inteiro, pode haver retenções na fonte ou o pagamento ainda não
              ocorreu. Nenhum valor aqui é estimado; todos vêm da soma exata dos registros
              oficiais.
            </p>

            <div className="legal-result-list">
              {result.rentals.map((rental) => (
                <article
                  className="legal-result-card"
                  key={`${rental.landlordName}|${rental.publicBody}|${rental.contractText ?? ""}`}
                >
                  <div>
                    <span>{rental.publicBody}</span>
                    <span>
                      {rental.contractText
                        ? `Contrato nº ${rental.contractText}`
                        : "número do contrato não identificado no histórico"}
                    </span>
                  </div>
                  <h2>{rental.landlordName}</h2>
                  <p>
                    <strong>{formatBrlDecimal(rental.committedAmount)}</strong> empenhados ·{" "}
                    <strong>{formatBrlDecimal(rental.paidAmount)}</strong> pagos ·{" "}
                    {rental.commitments} empenho{rental.commitments === 1 ? "" : "s"} de{" "}
                    {formatDate(rental.firstCommitmentDate)} a{" "}
                    {formatDate(rental.lastCommitmentDate)}
                  </p>
                  <p>
                    <strong>Endereço:</strong>{" "}
                    {rental.addressText ?? "não informado no histórico do empenho"}
                    {rental.useText ? (
                      <>
                        {" "}
                        · <strong>Uso:</strong> {rental.useText}
                      </>
                    ) : null}
                  </p>
                  {rental.description ? (
                    <p className="legal-result-excerpt">“{rental.description}”</p>
                  ) : null}
                  <p className="act-evidence">
                    Empenho mais recente {rental.latestCommitmentKey} ·{" "}
                    <a href={rental.sourcePageUrl} target="_blank" rel="noreferrer">
                      Portal da Transparência
                    </a>{" "}
                    · grade preservada, hash {rental.gridArtifactSha256.slice(0, 12)}…
                  </p>
                </article>
              ))}
            </div>
          </>
        )}

        <p className="hero-note">
          Metodologia municipal-property-rentals/1.3.0: empenhos do sistema de despesas da
          Prefeitura com subelemento “locação de imóveis”, na grade mais recente de cada mês;
          contrato lido do histórico quando citado (“Contrato nº …”); endereço e uso são trechos
          literais do histórico (“situado à …”, “funcionamento da …”), sem correção; CPF
          mascarado. Locação de
          veículos, máquinas e softwares fica de fora.
        </p>
      </section>
    </main>
  );
}
