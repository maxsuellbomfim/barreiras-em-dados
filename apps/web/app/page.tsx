import { formatBrlCompact } from "../lib/compact-money.mjs";
import { monthlyFinanceHref } from "../lib/monthly-finance-detail.mjs";
import { getPublicMonthlyFinanceClosures } from "../lib/monthly-finance";
import { getOfficialDiaryCatalog } from "../lib/official-diary-catalog";
import { getPublicPayrollMonths } from "../lib/public-payroll.mjs";
import { formatBrlDecimal } from "../lib/revenues";
import { getPublicSiconfiAnnualTotals } from "../lib/siconfi-annual-totals";
import { payrollMonthHref } from "./financas/finance-payroll-month-nav";

export const revalidate = 300;

const quickLinks = [
  {
    label: "Dinheiro público",
    detail: "Quanto a Prefeitura arrecada, paga e gasta com a folha, mês a mês.",
    href: "/financas",
    tone: "amber",
  },
  {
    label: "Compras públicas",
    detail: "Licitações, fornecedores, contratos e valores publicados.",
    href: "/licitacoes",
    tone: "amber",
  },
  {
    label: "Quem decide",
    detail: "Prefeitura, vereadores e deputados com fonte oficial.",
    href: "/representantes",
    tone: "green",
  },
  {
    label: "Diário Oficial",
    detail: "Texto integral, organizado por documento, com acesso à fonte oficial.",
    href: "/diario",
    tone: "blue",
  },
  {
    label: "Nomeações e exonerações",
    detail: "Quem entrou, quem saiu e qual documento comprova.",
    href: "/atos",
    tone: "violet",
  },
  {
    label: "Leis e indicações",
    detail: "O que a Câmara propõe, aprova e encaminha.",
    href: "/camara",
    tone: "blue",
  },
  {
    label: "Emendas para Barreiras",
    detail: "Quem destinou recursos, quanto foi pago e qual fonte comprova.",
    href: "/recursos",
    tone: "green",
  },
  {
    label: "Estado das fontes",
    detail: "Veja o que responde agora e o que está temporariamente indisponível.",
    href: "/estado",
    tone: "violet",
  },
] as const;

const monthYear = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

const fullDate = new Intl.DateTimeFormat("pt-BR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

function monthLabel(isoDate: string): string {
  return monthYear.format(new Date(`${isoDate}T12:00:00-03:00`));
}

function compact(value: string): string {
  return formatBrlCompact(value) ?? formatBrlDecimal(value);
}

type GlanceCard = Readonly<{
  unavailable?: boolean;
  question: string;
  value: string;
  exact: string | null;
  context: string;
  href: string;
  linkLabel: string;
}>;

type Loaded<T> = T extends Promise<infer R> ? R : never;

// Falha de consulta não some da página nem vira zero: o cartão continua,
// com o aviso e o caminho para a seção.
function unavailable(question: string, href: string): GlanceCard {
  return {
    unavailable: true,
    question,
    value: "Temporariamente indisponível",
    exact: null,
    context:
      "Falha ao consultar a fonte agora, não ausência de dados. Tente de novo em alguns minutos.",
    href,
    linkLabel: "Abrir a seção",
  };
}

function annualCard(
  annual: Loaded<ReturnType<typeof getPublicSiconfiAnnualTotals>>,
): GlanceCard | null {
  if (annual.state !== "available") return null;
  const year = [...annual.years]
    .sort((left, right) => right.fiscalYear - left.fiscalYear)
    .find((item) =>
      item.metrics.some((metric) => metric.metricKey === "gross_revenue_realized"),
    );
  const revenue = year?.metrics.find(
    (metric) => metric.metricKey === "gross_revenue_realized",
  );
  if (!year || !revenue) return null;
  const paid = year.metrics.find((metric) => metric.metricKey === "expense_paid");
  return {
    question: `Quanto a Prefeitura arrecadou em ${year.fiscalYear}?`,
    value: compact(revenue.amount),
    exact: formatBrlDecimal(revenue.amount),
    context: paid
      ? `Pagou ${compact(paid.amount)} no mesmo ano. Números do ano fechado, declarados ao Tesouro Nacional.`
      : "Número do ano fechado, declarado ao Tesouro Nacional.",
    href: `/financas/ano/${year.fiscalYear}`,
    linkLabel: `Ver o ano de ${year.fiscalYear}`,
  };
}

function monthlyCard(
  monthly: Loaded<ReturnType<typeof getPublicMonthlyFinanceClosures>>,
): GlanceCard | null {
  if (monthly.state !== "available") return null;
  const latest = [...monthly.closures]
    .filter((closure) => closure.revenueReportAmount && closure.expensePaidAmount)
    .sort((left, right) => right.periodEnd.localeCompare(left.periodEnd))[0];
  if (!latest?.revenueReportAmount || !latest.expensePaidAmount) return null;
  return {
    question: `Quanto entrou e quanto saiu em ${monthLabel(latest.periodStart)}?`,
    value: compact(latest.revenueReportAmount),
    exact: `Entrou ${formatBrlDecimal(latest.revenueReportAmount)}`,
    context: `Saíram ${compact(latest.expensePaidAmount)} em pagamentos no mesmo mês. A diferença não é saldo bancário.`,
    href: monthlyFinanceHref(latest.periodStart),
    linkLabel: "Ver o mês",
  };
}

function payrollCard(
  payroll: Loaded<ReturnType<typeof getPublicPayrollMonths>>,
): GlanceCard | null {
  if (payroll.state !== "available") return null;
  const latest = [...payroll.months].sort((left, right) =>
    right.referenceMonth.localeCompare(left.referenceMonth),
  )[0];
  if (!latest) return null;
  return {
    question: `Quanto custou a folha de ${monthLabel(latest.referenceMonth)}?`,
    value: compact(latest.grossAmount),
    exact: `${formatBrlDecimal(latest.grossAmount)} brutos`,
    context: `${latest.employeeCount.toLocaleString("pt-BR")} vínculos na folha regular da Prefeitura, sem nomes nem salários individuais.`,
    href: payrollMonthHref(latest.referenceMonth),
    linkLabel: "Ver a folha do mês",
  };
}

function diaryCard(
  diary: Loaded<ReturnType<typeof getOfficialDiaryCatalog>>,
): GlanceCard | null {
  if (diary.state !== "available") return null;
  const latest = [...diary.entries].sort(
    (left, right) =>
      right.editionDate.localeCompare(left.editionDate) || right.edition - left.edition,
  )[0];
  if (!latest) return null;
  return {
    question: "O que saiu no Diário Oficial?",
    value: `Edição ${latest.edition}`,
    exact: null,
    context: `Publicada em ${fullDate.format(new Date(`${latest.editionDate}T12:00:00-03:00`))}. Texto organizado por documento, com o PDF oficial ao lado.`,
    href: `/diario/${latest.editionYear}/${latest.edition}`,
    linkLabel: "Abrir a edição",
  };
}

async function loadGlance(): Promise<readonly GlanceCard[]> {
  const [annual, monthly, payroll, diary] = await Promise.all([
    getPublicSiconfiAnnualTotals(),
    getPublicMonthlyFinanceClosures(),
    getPublicPayrollMonths(3),
    getOfficialDiaryCatalog(),
  ]);
  return [
    annualCard(annual) ??
      unavailable("Quanto a Prefeitura arrecadou no último ano fechado?", "/financas"),
    monthlyCard(monthly) ??
      unavailable("Quanto entrou e quanto saiu no último mês?", "/financas"),
    payrollCard(payroll) ??
      unavailable("Quanto custou a folha no último mês?", "/financas#finance-payroll-title"),
    diaryCard(diary) ?? unavailable("O que saiu no Diário Oficial?", "/diario"),
  ];
}

export default async function HomePage() {
  const glance = await loadGlance();

  return (
    <main>
      <section className="home-intro" aria-labelledby="home-title">
        <span className="eyebrow">Transparência pública de Barreiras (BA)</span>
        <h1 id="home-title">Para onde vai o dinheiro de Barreiras — e quem decide.</h1>
        <p>
          Números oficiais da Prefeitura, da Câmara e do Diário Oficial, explicados
          em linguagem simples e sempre com o documento de origem ao lado.
        </p>
      </section>

      <section className="home-glance" aria-labelledby="glance-title">
        <h2 id="glance-title" className="sr-only">
          Barreiras em números
        </h2>
        <div className="glance-grid">
          {glance.map((card) => (
            <a
              className={card.unavailable ? "glance-card glance-card-unavailable" : "glance-card"}
              href={card.href}
              key={card.question}
            >
              <span className="glance-question">{card.question}</span>
              <strong className="glance-value">{card.value}</strong>
              {card.exact ? <span className="glance-exact">{card.exact}</span> : null}
              <span className="glance-context">{card.context}</span>
              <span className="glance-link">
                {card.linkLabel} <span aria-hidden="true">→</span>
              </span>
            </a>
          ))}
        </div>
      </section>

      <section className="section section-quick-access" id="dados" aria-labelledby="data-title">
        <div className="section-heading">
          <h2 id="data-title">O que você quer acompanhar?</h2>
          <p>
            Cada página mostra o que encontramos, de onde veio e o documento que
            sustenta a informação.
          </p>
        </div>

        <div className="quick-grid">
          {quickLinks.map((link) => (
            <a className="quick-card" href={link.href} key={link.href}>
              <span className={`quick-dot quick-dot-${link.tone}`} />
              <span className="quick-card-copy">
                <strong>{link.label}</strong>
                <span>{link.detail}</span>
              </span>
              <span className="quick-card-arrow" aria-hidden="true">→</span>
            </a>
          ))}
        </div>

        <p className="home-method">
          Fonte verificável em cada registro, cálculos feitos por código e nenhuma
          conclusão automática sobre pessoas.{" "}
          <a href="/sobre">Como funciona e como contestar um dado →</a>
        </p>
      </section>
    </main>
  );
}
