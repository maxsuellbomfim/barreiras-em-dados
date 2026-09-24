import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { periodStartFromSlug } from "../../../../lib/monthly-finance-detail.mjs";
import {
  getPublicPayrollCompensationDistribution,
  getPublicPayrollMonths,
  getPublicPayrollRegimeBreakdown,
  payrollCompensationMatchesMonth,
  payrollRegimeBreakdownMatchesMonth,
} from "../../../../lib/public-payroll.mjs";
import FinancePayrollMonthCard, {
  formatPayrollMonthTitle,
} from "../../finance-payroll-month-card";
import FinancePayrollMonthNav from "../../finance-payroll-month-nav";

export const revalidate = 300;

type PageProps = Readonly<{
  params: Promise<{ mes: string }>;
}>;

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { mes } = await params;
  const referenceMonth = periodStartFromSlug(mes);
  if (!referenceMonth) return { title: "Competência inválida | Folha" };
  const title = formatPayrollMonthTitle(referenceMonth);
  return {
    title: `Folha de ${title} | Finanças`,
    description: `Quanto custou a folha da Prefeitura de Barreiras em ${title}: totais, divisão por vínculo, faixas de provento e PDFs oficiais, sem dados pessoais.`,
  };
}

function PageShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/financas#finance-payroll-title">
            <span>← Folha em Finanças</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/financas">Finanças</a>
            <a href="/financas/cobertura">Cobertura</a>
            <a href="/licitacoes">Compras</a>
          </nav>
        </div>
      </header>
      {children}
    </main>
  );
}

export default async function PayrollMonthPage({ params }: PageProps) {
  const { mes } = await params;
  const referenceMonth = periodStartFromSlug(mes);
  if (!referenceMonth) notFound();

  const monthsResult = await getPublicPayrollMonths(120);
  if (monthsResult.state === "unavailable") {
    return (
      <PageShell>
        <section className="section finance-month-empty" aria-labelledby="payroll-unavailable-title">
          <span className="eyebrow">Consulta temporariamente indisponível</span>
          <h1 id="payroll-unavailable-title">Não foi possível consultar a folha agora</h1>
          <p>
            Nenhum valor será substituído por zero ou estimado. Tente novamente
            mais tarde.
          </p>
          <a className="finance-month-back" href="/financas">← Voltar para Finanças</a>
        </section>
      </PageShell>
    );
  }

  const months = monthsResult.months;
  const month = months.find((item) => item.referenceMonth === referenceMonth);
  if (!month) {
    return (
      <PageShell>
        <section className="section finance-month-empty" aria-labelledby="payroll-missing-title">
          <span className="eyebrow">Folha mensal</span>
          <h1 id="payroll-missing-title">
            A folha de {formatPayrollMonthTitle(referenceMonth)} ainda não foi publicada
          </h1>
          <p>
            Isso não significa gasto zero. O calendário de cobertura mostra se o
            documento não foi localizado, está em validação ou possui conflito.
          </p>
          <a className="finance-month-back" href="/financas/cobertura">
            Ver a cobertura da folha →
          </a>
          {months.length > 0 ? (
            <FinancePayrollMonthNav months={months} currentMonth={referenceMonth} />
          ) : null}
        </section>
      </PageShell>
    );
  }

  const [regimeResult, compensationResult] = await Promise.all([
    getPublicPayrollRegimeBreakdown(month.referenceMonth),
    getPublicPayrollCompensationDistribution(month.referenceMonth),
  ]);
  const regimeRows =
    regimeResult.state === "available" &&
    payrollRegimeBreakdownMatchesMonth(regimeResult.rows, month)
      ? regimeResult.rows
      : [];
  const compensationRows =
    compensationResult.state === "available" &&
    payrollCompensationMatchesMonth(compensationResult.rows, month)
      ? compensationResult.rows
      : [];
  const pendingDetails = [
    regimeRows.length === 0 ? "a divisão por vínculo" : null,
    compensationRows.length === 0 ? "as faixas de provento" : null,
  ].filter(Boolean);

  return (
    <PageShell>
      <section
        className="section finance-payroll-section finance-payroll-month-page"
        aria-labelledby="payroll-month-title"
      >
        <div className="section-heading">
          <span className="eyebrow">Folha mensal verificável</span>
          <h1 id="payroll-month-title">
            Folha de {formatPayrollMonthTitle(month.referenceMonth)}
          </h1>
          <p>
            Total consolidado de todos os processamentos oficiais do mês, sem
            publicar nomes, matrículas, contas bancárias ou descontos individuais.
          </p>
        </div>
        <FinancePayrollMonthNav months={months} currentMonth={month.referenceMonth} />
        <FinancePayrollMonthCard
          month={month}
          regimeRows={regimeRows}
          compensationRows={compensationRows}
        />
        {pendingDetails.length > 0 ? (
          <p className="finance-payroll-pending" role="status">
            Ainda em processamento para este mês: {pendingDetails.join(" e ")}.
            O total acima já está validado; os detalhes aparecem aqui quando
            fecharem centavo a centavo com o PDF oficial.
          </p>
        ) : null}
      </section>
    </PageShell>
  );
}
