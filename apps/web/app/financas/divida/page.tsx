import type { Metadata } from "next";

import { formatBrlCompact } from "../../../lib/compact-money.mjs";
import { getPublicDebtStatements } from "../../../lib/public-debt.mjs";
import { formatBrlDecimal } from "../../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Dívida da Prefeitura | Finanças",
  description:
    "Quanto a Prefeitura de Barreiras deve, como ela mesma declara ao Tesouro Nacional no Relatório de Gestão Fiscal: dívida consolidada, composição e série histórica.",
};

function money(value: string | null): string {
  return value === null ? "não informado na fonte" : formatBrlDecimal(value);
}

function percent(value: string | null): string {
  return value === null ? "não informado" : `${value.replace(".", ",")}%`;
}

function periodLabel(period: number, year: number): string {
  return `${period}º quadrimestre de ${year}`;
}

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export default async function PublicDebtPage() {
  const result = await getPublicDebtStatements();
  const latest = result.state === "available" ? result.statements[0] : undefined;

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/financas">← Finanças</a>
      </nav>

      <section className="section" aria-labelledby="debt-title">
        <div className="section-heading">
          <span className="eyebrow">Declarado pela Prefeitura ao Tesouro Nacional</span>
          <h1 id="debt-title">Quanto a Prefeitura deve</h1>
          <p>
            A cada quatro meses a Prefeitura publica o Relatório de Gestão Fiscal (Lei de
            Responsabilidade Fiscal, art. 55). O Anexo 2 traz a <strong>dívida consolidada</strong>:
            empréstimos, parcelamentos de dívidas, precatórios vencidos e outras dívidas de longo
            prazo. Os números abaixo são exatamente os declarados; o portal não soma nada.
          </p>
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Dívida temporariamente indisponível</strong>
              <p>A falha é de consulta; ela não significa dívida zero.</p>
            </div>
          </div>
        ) : latest === undefined ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Relatório de Gestão Fiscal ainda não coletado</strong>
              <p>Sem demonstrativo preservado, o portal não mostra valor nenhum.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="glance-grid">
              <article className="glance-card">
                <span className="glance-question">Dívida consolidada líquida</span>
                <span className="glance-value">
                  {latest.netConsolidatedDebt
                    ? formatBrlCompact(latest.netConsolidatedDebt)
                    : "não informada"}
                </span>
                <span className="glance-exact">{money(latest.netConsolidatedDebt)}</span>
                <span className="glance-context">
                  Dívida consolidada menos o caixa disponível, ao fim do{" "}
                  {periodLabel(latest.period, latest.fiscalYear)}.
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Dívida consolidada</span>
                <span className="glance-value">
                  {latest.consolidatedDebt ? formatBrlCompact(latest.consolidatedDebt) : "—"}
                </span>
                <span className="glance-exact">{money(latest.consolidatedDebt)}</span>
                <span className="glance-context">
                  Antes das deduções ({money(latest.deductions)}).
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Em relação à receita</span>
                <span className="glance-value">{percent(latest.netDebtRevenuePercent)}</span>
                <span className="glance-context">
                  da receita corrente líquida ajustada ({money(latest.adjustedNetCurrentRevenue)}).
                  O limite do Senado é {money(latest.senateLimit)}; o de alerta,{" "}
                  {money(latest.alertLimit)}.
                </span>
              </article>
            </div>

            <h2>Do que é feita a dívida ({periodLabel(latest.period, latest.fiscalYear)})</h2>
            <div
              className="finance-coverage-matrix finance-coverage-table-scroll"
              role="region"
              aria-label="Composição da dívida consolidada"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Linha do demonstrativo</th>
                    <th scope="col">Valor declarado</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.composition.map((line) => (
                    <tr key={line.code}>
                      <th scope="row">{line.account}</th>
                      <td>
                        {line.code.startsWith("Percentual")
                          ? percent(line.value)
                          : formatBrlDecimal(line.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h2>Como a dívida evoluiu</h2>
            <div
              className="finance-coverage-matrix finance-coverage-table-scroll"
              role="region"
              aria-label="Série da dívida consolidada"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Quadrimestre</th>
                    <th scope="col">Dívida consolidada</th>
                    <th scope="col">Dívida consolidada líquida</th>
                    <th scope="col">% da receita</th>
                  </tr>
                </thead>
                <tbody>
                  {result.statements.map((statement) => (
                    <tr key={`${statement.fiscalYear}-${statement.period}`}>
                      <th scope="row">
                        {statement.period}º/{statement.fiscalYear}
                      </th>
                      <td>{money(statement.consolidatedDebt)}</td>
                      <td>{money(statement.netConsolidatedDebt)}</td>
                      <td>{percent(statement.netDebtRevenuePercent)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="act-evidence">
              Demonstrativo preservado em {formatDate(latest.retrievedAt)} · hash{" "}
              {latest.artifactSha256.slice(0, 12)}… ·{" "}
              <a href={latest.sourceUrl} target="_blank" rel="noreferrer">
                consultar no SICONFI
              </a>
            </p>
          </>
        )}

        <p className="hero-note">
          Metodologia municipal-debt-rgf-annex2/1.0.0: RGF-Anexo 02 do Poder Executivo de
          Barreiras na API oficial do SICONFI, coluna acumulada de cada quadrimestre; quando o
          Município retifica o relatório, vale a versão coletada mais recente. Quadrimestre sem
          linha na tabela ainda não foi publicado ou coletado — nunca significa dívida zero.
          Restos a pagar e dívidas de curto prazo não entram na dívida consolidada.
        </p>
      </section>
    </main>
  );
}
