import type { Metadata } from "next";

import { formatBrlCompact } from "../../../lib/compact-money.mjs";
import {
  FIRST_WITHHOLDING_YEAR,
  getPublicPayrollWithholdings,
  withholdingYear,
} from "../../../lib/payroll-withholdings.mjs";
import { formatBrlDecimal } from "../../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Retenções da folha | Finanças",
  description:
    "INSS do servidor, empréstimos consignados, contribuições sindicais e pensões descontados da folha da Prefeitura de Barreiras, como publicados no Portal da Transparência.",
};

type PageProps = Readonly<{ searchParams: Promise<{ ano?: string }> }>;

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function formatMonth(month: string): string {
  const [year, number] = month.split("-");
  return `${MONTHS[Number(number) - 1]}/${year}`;
}

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

export default async function PayrollWithholdingsPage({ searchParams }: PageProps) {
  const currentYear = new Date().getFullYear();
  const year = withholdingYear((await searchParams).ano, currentYear);
  const result = await getPublicPayrollWithholdings(year);
  const years = Array.from(
    { length: currentYear - FIRST_WITHHOLDING_YEAR + 1 },
    (_, index) => currentYear - index,
  );

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/financas">← Finanças</a>
      </nav>

      <section className="section" aria-labelledby="withholdings-title">
        <div className="section-heading">
          <span className="eyebrow">Empenhos extraorçamentários</span>
          <h1 id="withholdings-title">Retenções da folha de pagamento</h1>
          <p>
            Do salário de cada servidor a Prefeitura desconta a contribuição ao INSS, parcelas de
            empréstimo consignado, contribuição sindical e pensão alimentícia. Esse dinheiro não é
            do Município: ele precisa ser repassado ao INSS, aos bancos, aos sindicatos e aos
            beneficiários. O Portal da Transparência publica essas retenções como{" "}
            <strong>empenhos extraorçamentários</strong>, listados abaixo por credor.
          </p>
        </div>

        <nav className="rentals-years" aria-label="Ano dos empenhos">
          {years.map((option) => (
            <a
              key={option}
              href={`/financas/retencoes?ano=${option}`}
              aria-current={option === year ? "page" : undefined}
            >
              {option}
            </a>
          ))}
        </nav>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Retenções temporariamente indisponíveis</strong>
              <p>A falha é de consulta; ela não significa que não haja retenções.</p>
            </div>
          </div>
        ) : result.creditors.length === 0 || result.summary === null ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhum empenho de retenção da folha em {year}</strong>
              <p>Nenhum empenho extraorçamentário coletado deste ano cita retenção da folha.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="glance-grid">
              <article className="glance-card">
                <span className="glance-question">Empenhado para repasse</span>
                <span className="glance-value">{formatBrlCompact(result.summary.amount)}</span>
                <span className="glance-exact">{formatBrlDecimal(result.summary.amount)}</span>
                <span className="glance-context">
                  {result.summary.commitments.toLocaleString("pt-BR")} empenhos em {year}, já
                  descontados os estornos ({formatBrlDecimal(result.summary.reversalAmount)}).
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Pagamentos publicados</span>
                <span className="glance-value">
                  {result.summary.linkedPayments.toLocaleString("pt-BR")}
                </span>
                <span className="glance-context">
                  {result.summary.linkedPayments === 0
                    ? "Nenhuma ordem de pagamento publicada aponta para estes empenhos. Por isso não é possível conferir aqui se e quando cada repasse foi feito."
                    : "Ordens de pagamento publicadas que apontam para estes empenhos pela chave oficial."}
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

            <div
              className="territorial-table-wrap"
              role="region"
              aria-label="Retenções por credor"
              tabIndex={0}
            >
              <table className="territorial-table recipients-table">
                <caption>Retenções da folha de {year} por credor</caption>
                <thead>
                  <tr>
                    <th scope="col">Credor</th>
                    <th scope="col">Empenhado</th>
                    <th scope="col">Estornos</th>
                    <th scope="col">Empenhos</th>
                    <th scope="col">Período</th>
                    <th scope="col">Fonte</th>
                  </tr>
                </thead>
                <tbody>
                  {result.creditors.map((creditor) => (
                    <tr key={creditor.creditorName ?? "pessoas-fisicas"}>
                      <th scope="row">
                        {creditor.creditorName ??
                          "Pessoas físicas (pensão alimentícia e outros descontos pessoais; nomes não publicados)"}
                      </th>
                      <td className="territorial-table-number">
                        {formatBrlDecimal(creditor.amount)}
                      </td>
                      <td className="territorial-table-number">
                        {creditor.reversalAmount === "0.00"
                          ? "—"
                          : formatBrlDecimal(creditor.reversalAmount)}
                      </td>
                      <td className="territorial-table-number">
                        {creditor.commitments.toLocaleString("pt-BR")}
                      </td>
                      <td>
                        {formatDate(creditor.firstCommitmentDate)} a{" "}
                        {formatDate(creditor.lastCommitmentDate)}
                      </td>
                      <td>
                        {creditor.latestCommitmentKey} · hash{" "}
                        {creditor.gridArtifactSha256.slice(0, 12)}…
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div
              className="territorial-table-wrap"
              role="region"
              aria-label="Retenções por mês"
              tabIndex={0}
            >
              <table className="territorial-table">
                <caption>Retenções da folha de {year} por mês do empenho</caption>
                <thead>
                  <tr>
                    <th scope="col">Mês</th>
                    <th scope="col">Empenhado</th>
                    <th scope="col">Empenhos</th>
                  </tr>
                </thead>
                <tbody>
                  {result.summary.months.map((month) => (
                    <tr key={month.month}>
                      <th scope="row">{formatMonth(month.month)}</th>
                      <td className="territorial-table-number">
                        {formatBrlDecimal(month.amount)}
                      </td>
                      <td className="territorial-table-number">
                        {month.commitments.toLocaleString("pt-BR")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="hero-note">
              Empenho é a reserva do valor, não o repasse. O imposto de renda retido do servidor
              não é repasse a terceiros: pela Constituição (art. 158, I), ele pertence ao próprio
              Município. Fonte:{" "}
              <a href={result.summary.sourcePageUrl} target="_blank" rel="noreferrer">
                Portal da Transparência
              </a>
              , grade de empenhos mais recente de cada mês.
            </p>
          </>
        )}

        <p className="hero-note">
          Metodologia municipal-payroll-withholdings/1.0.0: empenhos do tipo
          “Extra-Orçamentária” cujo histórico cita retenção, consignado, INSS, segurado,
          previdência, contribuição sindical ou pensão, junto com “folha” ou “pensão”;
          retenções de notas fiscais de fornecedores ficam de fora. Estornos entram com valor
          negativo. Credores pessoa física e toda pensão alimentícia são somados numa linha sem
          nome, e o histórico dos empenhos não é exibido, porque traz o nome do servidor e o do
          beneficiário.
        </p>
      </section>
    </main>
  );
}
