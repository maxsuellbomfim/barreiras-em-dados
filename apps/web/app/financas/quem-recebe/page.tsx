import type { Metadata } from "next";

import { formatBrlCompact } from "../../../lib/compact-money.mjs";
import {
  compareWithDeclared,
  FIRST_PAYMENT_YEAR,
  formatCnpj,
  getPublicPaymentRecipients,
  paymentYear,
} from "../../../lib/payment-recipients.mjs";
import type { PaymentRecipient } from "../../../lib/payment-recipients.mjs";
import { formatBrlDecimal } from "../../../lib/revenues";
import { getPublicSiconfiAnnualTotals } from "../../../lib/siconfi-annual-totals";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Quem recebe o dinheiro | Finanças",
  description:
    "Para quem a Prefeitura de Barreiras pagou em cada ano: soma exata das ordens de pagamento por grupo de despesa, por órgão e por credor, com a fonte oficial.",
};

type PageProps = Readonly<{ searchParams: Promise<{ ano?: string }> }>;

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Bahia",
  }).format(new Date(iso));
}

function plural(value: number, singular: string, pluralForm: string): string {
  return `${value.toLocaleString("pt-BR")} ${value === 1 ? singular : pluralForm}`;
}

function RecipientRow({ recipient }: Readonly<{ recipient: PaymentRecipient }>) {
  return (
    <tr>
      <th scope="row">
        {recipient.creditorName ??
          `Pessoas físicas e credores sem forma jurídica no nome (${plural(
            recipient.creditors,
            "credor",
            "credores",
          )})`}
        {recipient.registry ? (
          <small>
            CNPJ {formatCnpj(recipient.registry.cnpj)} · {recipient.registry.legalName} ·{" "}
            {recipient.registry.legalNature.toLowerCase()} (cadastro da Receita de{" "}
            {recipient.registry.month.split("-").reverse().join("/")})
          </small>
        ) : null}
        <small>grade preservada, hash {recipient.gridArtifactSha256.slice(0, 12)}…</small>
      </th>
      <td className="territorial-table-number">{formatBrlDecimal(recipient.paidAmount)}</td>
      <td className="territorial-table-number">{recipient.payments.toLocaleString("pt-BR")}</td>
      <td>
        {formatDate(recipient.firstPaymentDate)} a {formatDate(recipient.lastPaymentDate)}
      </td>
      <td>{recipient.mainNature?.toLowerCase() ?? "—"}</td>
    </tr>
  );
}

export default async function PaymentRecipientsPage({ searchParams }: PageProps) {
  const currentYear = new Date().getFullYear();
  const year = paymentYear((await searchParams).ano, currentYear);
  const [result, declared] = await Promise.all([
    getPublicPaymentRecipients(year),
    getPublicSiconfiAnnualTotals(),
  ]);
  const declaredYear =
    declared.state === "available"
      ? declared.years.find((entry) => entry.fiscalYear === year)
      : undefined;
  const declaredMetric = (key: string) =>
    declaredYear?.metrics.find((metric) => metric.metricKey === key);
  const declaredPaid = declaredMetric("expense_paid");
  const declaredCommitted = declaredMetric("expense_committed");
  const years = Array.from(
    { length: currentYear - FIRST_PAYMENT_YEAR + 1 },
    (_, index) => currentYear - index,
  );

  return (
    <main>
      <nav className="page-back" aria-label="Voltar">
        <a href="/financas">← Finanças</a>
      </nav>

      <section className="section" aria-labelledby="recipients-title">
        <div className="section-heading">
          <span className="eyebrow">Ordens de pagamento oficiais</span>
          <h1 id="recipients-title">Quem recebe o dinheiro da Prefeitura</h1>
          <p>
            Cada pagamento orçamentário publicado no Portal da Transparência, somado por credor
            e agrupado pela natureza da despesa escrita pela própria Prefeitura. Empresas e
            instituições aparecem pelo nome; pessoas físicas, como servidores e beneficiários,
            entram só no total.
          </p>
        </div>

        <nav className="rentals-years" aria-label="Ano dos pagamentos">
          {years.map((option) => (
            <a
              key={option}
              href={`/financas/quem-recebe?ano=${option}`}
              aria-current={option === year ? "page" : undefined}
            >
              {option}
            </a>
          ))}
        </nav>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Pagamentos temporariamente indisponíveis</strong>
              <p>A falha é de consulta; ela não significa que não houve pagamentos.</p>
            </div>
          </div>
        ) : result.groups.length === 0 || result.summary === null ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhuma grade de pagamentos de {year} processada</strong>
              <p>Sem grade preservada não há total; isso não significa que nada foi pago.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="glance-grid">
              <article className="glance-card">
                <span className="glance-question">Pago em {year}</span>
                <span className="glance-value">{formatBrlCompact(result.summary.paidAmount)}</span>
                <span className="glance-exact">{formatBrlDecimal(result.summary.paidAmount)}</span>
                <span className="glance-context">
                  {plural(result.summary.payments, "ordem de pagamento", "ordens de pagamento")}.
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">De empenhos de anos anteriores</span>
                <span className="glance-value">
                  {formatBrlCompact(result.summary.priorCommitmentAmount)}
                </span>
                <span className="glance-exact">
                  {formatBrlDecimal(result.summary.priorCommitmentAmount)}
                </span>
                <span className="glance-context">
                  {result.summary.uncollectedCommitmentAmount === "0.00"
                    ? `Restos a pagar: despesas empenhadas antes de ${year} e pagas neste ano.`
                    : `Restos a pagar identificados. Outros ${formatBrlDecimal(
                        result.summary.uncollectedCommitmentAmount,
                      )} pagaram empenhos fora da coleta (anteriores a 2024), sem ano identificável.`}
                </span>
              </article>
              <article className="glance-card">
                <span className="glance-question">Meses coletados</span>
                <span className="glance-value">{result.summary.gridMonths} de 12</span>
                <span className="glance-context">
                  Atualizado em {formatDateTime(result.summary.refreshedAt)}.
                </span>
              </article>
            </div>

            <section className="recipients-declared" aria-labelledby="declared-title">
              <h2 id="declared-title">Comparação com o declarado ao Tesouro</h2>
              {declaredPaid ? (
                (() => {
                  const comparison = compareWithDeclared(
                    result.summary.paidAmount,
                    declaredPaid.amount,
                  );
                  return (
                    <p>
                      A Prefeitura declarou ao Tesouro Nacional (SICONFI, {declaredPaid.officialAnnex},
                      “{declaredPaid.officialColumnLabel}”) {formatBrlDecimal(declaredPaid.amount)}{" "}
                      pagos em {year}. As ordens de pagamento publicadas no portal somam{" "}
                      {formatBrlDecimal(result.summary.paidAmount)}
                      {comparison
                        ? ` (${comparison.coveragePercent}% do declarado). A diferença de ${formatBrlDecimal(
                            comparison.differenceAmount,
                          )} não aparece nas ordens de pagamento do portal; a plataforma não sabe a causa e não a estima.`
                        : "."}
                    </p>
                  );
                })()
              ) : (
                <p>
                  O demonstrativo anual (DCA) de {year} ainda não foi publicado no SICONFI ou não
                  está disponível agora; sem ele não há comparação.
                </p>
              )}
              <p className="hero-note">
                Esta página não soma empenhos: o portal não publica as anulações de empenho, então
                somar os empenhos emitidos superestimaria o valor empenhado
                {declaredCommitted
                  ? ` (o empenhado oficial declarado em ${year} é ${formatBrlDecimal(declaredCommitted.amount)})`
                  : ""}
                .
              </p>
            </section>

            <div
              className="territorial-table-wrap"
              role="region"
              aria-label="Pagamentos por grupo"
              tabIndex={0}
            >
              <table className="territorial-table recipients-table">
                <caption>Pagamentos de {year} por grupo de despesa</caption>
                <thead>
                  <tr>
                    <th scope="col">Grupo</th>
                    <th scope="col">Pago</th>
                    <th scope="col">Pagamentos</th>
                    <th scope="col">Credores</th>
                  </tr>
                </thead>
                <tbody>
                  {result.groups.map((group) => (
                    <tr key={group.key}>
                      <th scope="row">
                        <a href={`#grupo-${group.key}`}>{group.label}</a>
                      </th>
                      <td className="territorial-table-number">
                        {formatBrlDecimal(group.paidAmount)}
                      </td>
                      <td className="territorial-table-number">
                        {group.payments.toLocaleString("pt-BR")}
                      </td>
                      <td className="territorial-table-number">
                        {group.creditors.toLocaleString("pt-BR")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div
              className="territorial-table-wrap"
              role="region"
              aria-label="Pagamentos por órgão"
              tabIndex={0}
            >
              <table className="territorial-table recipients-table">
                <caption>Quem pagou: órgão ou fundo municipal</caption>
                <thead>
                  <tr>
                    <th scope="col">Órgão</th>
                    <th scope="col">Pago</th>
                    <th scope="col">Pagamentos</th>
                  </tr>
                </thead>
                <tbody>
                  {result.summary.bodies.map((body) => (
                    <tr key={body.publicBody}>
                      <th scope="row">{body.publicBody}</th>
                      <td className="territorial-table-number">
                        {formatBrlDecimal(body.paidAmount)}
                      </td>
                      <td className="territorial-table-number">
                        {body.payments.toLocaleString("pt-BR")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {result.groups.map((group) => {
              const namedTotal =
                group.creditors - group.others.reduce((sum, other) => sum + other.creditors, 0);
              return (
                <details
                  key={group.key}
                  id={`grupo-${group.key}`}
                  className="recipients-group"
                  open={group.key === "compras_servicos"}
                >
                  <summary>
                    <strong>{group.label}</strong> · {formatBrlDecimal(group.paidAmount)} ·{" "}
                    {plural(group.creditors, "credor", "credores")}
                    {group.recipients.length < namedTotal
                      ? ` (mostrando os ${group.recipients.length} com nome que mais receberam)`
                      : ""}
                  </summary>
                  <div
                    className="territorial-table-wrap"
                    role="region"
                    aria-label={`Credores: ${group.label}`}
                    tabIndex={0}
                  >
                    <table className="territorial-table">
                      <thead>
                        <tr>
                          <th scope="col">Credor</th>
                          <th scope="col">Pago</th>
                          <th scope="col">Pagamentos</th>
                          <th scope="col">Período</th>
                          <th scope="col">Natureza mais frequente</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.recipients.map((recipient) => (
                          <RecipientRow key={recipient.creditorName} recipient={recipient} />
                        ))}
                        {group.others.map((other) => (
                          <RecipientRow key={`pf|${other.mainNature ?? ""}`} recipient={other} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              );
            })}

            <ul className="hero-note">
              <li>
                Soma das ordens de pagamento orçamentárias publicadas no portal da Prefeitura,
                pela data do pagamento; não é a “despesa paga” do RREO nem a despesa com pessoal
                da LRF.
              </li>
              <li>
                Inclui pagamentos de restos a pagar, isto é, despesas empenhadas em anos
                anteriores.
              </li>
              <li>
                Não entram pagamentos extraorçamentários, como o repasse de retenções e
                consignações; por isso o valor por credor pode diferir do valor bruto da nota.
              </li>
              <li>
                Parte da folha aparece como pagamento à própria Prefeitura ou a fundos municipais
                (FOPAG), que repassam os salários; servidores e beneficiários não são
                identificados.
              </li>
              <li>
                Os grupos seguem a descrição da natureza informada pela Prefeitura, por regra
                automática versionada, e não indicam irregularidade.
              </li>
              {result.summary.unreadableRows + result.summary.excludedRows > 0 ? (
                <li>
                  {plural(result.summary.unreadableRows, "linha", "linhas")} com valor ilegível
                  e {plural(result.summary.excludedRows, "linha", "linhas")} fora do escopo
                  (extraorçamentária ou de outro ano) ficaram fora da soma.
                </li>
              ) : null}
            </ul>
          </>
        )}

        <p className="hero-note">
          Metodologia municipal-payment-recipients/1.2.0 (ADR 0095): grade mais recente de cada
          mês do sistema de despesas da Prefeitura; só ordens orçamentárias; grupo por regra
          fixa sobre a descrição da natureza; credor com nome apenas quando o nome traz forma
          jurídica ou é ente público, nunca com CPF; pessoas físicas somadas por natureza da
          despesa; CNPJ do cadastro da Receita só por contrato confirmado do pagamento ou pelo
          código oficial do credor já ligado a um único CNPJ, e só quando tudo aponta o mesmo
          CNPJ. Todos os credores aparecem. Nenhum valor é estimado.
        </p>
      </section>
    </main>
  );
}
