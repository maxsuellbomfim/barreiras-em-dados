import type { Metadata } from "next";
import { connection } from "next/server";

import { getPublicFinanceCoverage } from "../../../lib/finance-coverage";
import {
  getPublicFiscalReportCoverageResult,
  getPublicMunicipalFinanceDocumentCoverageResult,
} from "../../../lib/finance-document-coverage-results";
import { getPublicObligationCoverage } from "../../../lib/public-obligations.mjs";
import { getPublicPayrollCoverage } from "../../../lib/public-payroll.mjs";
import FinanceCoverageMatrix from "../finance-coverage-matrix";
import FinanceFiscalReportCoverageMatrix from "../finance-fiscal-report-coverage-matrix";
import FinanceMunicipalDocumentCoverage from "../finance-municipal-document-coverage";
import FinanceObligationCoverageMatrix from "../finance-obligation-coverage-matrix";
import FinancePayrollCoverageMatrix from "../finance-payroll-coverage-matrix";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Cobertura financeira por período",
  description:
    "Calendários de receitas, despesas, folha, restos a pagar e demonstrativos fiscais de Barreiras desde 2021.",
};

export default async function FinanceCoveragePage() {
  await connection();
  const [
    financeCoverage,
    payrollCoverage,
    obligationCoverage,
    municipalDocumentCoverage,
    fiscalCoverage,
  ] = await Promise.all([
    getPublicFinanceCoverage(),
    getPublicPayrollCoverage(120),
    getPublicObligationCoverage(),
    getPublicMunicipalFinanceDocumentCoverageResult(),
    getPublicFiscalReportCoverageResult(),
  ]);

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/financas" aria-label="Voltar para Finanças">
            <span>← Finanças</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/licitacoes">Compras</a>
            <a href="/representantes">Quem decide</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="finance-coverage-page-title">
        <div className="section-heading">
          <span className="eyebrow">Auditoria documental</span>
          <h1 id="finance-coverage-page-title">Cobertura financeira por período</h1>
          <p>
            Confira mês, bimestre, quadrimestre e ano sem transformar documento
            ausente em valor zero. Cada calendário preserva o ritmo da fonte e
            informa o que foi publicado, o que ainda está em validação e o que não
            foi localizado nas consultas oficiais.
          </p>
        </div>

        <nav className="finance-coverage-jump-nav" aria-label="Ir para um calendário">
          <a href="#finance-coverage-title">Receitas e despesas</a>
          <a href="#payroll-matrix-title">Folha</a>
          <a href="#obligation-matrix-title">Restos a pagar</a>
          <a href="#municipal-document-coverage-title">Documentos mensais</a>
          <a href="#fiscal-report-coverage-title">RREO e RGF</a>
        </nav>

        <section className="finance-coverage-section" aria-labelledby="finance-coverage-title">
          <div className="section-heading compact">
            <span className="eyebrow">Receitas e despesas</span>
            <h2 id="finance-coverage-title">Quais meses podem ser comparados</h2>
            <p>
              A comparação só é liberada quando os relatórios oficiais do mesmo
              período estão reconciliados. Ausência e conflito permanecem visíveis.
            </p>
          </div>
          <FinanceCoverageMatrix initialResult={financeCoverage} />
        </section>

        <section className="finance-coverage-section" aria-labelledby="payroll-matrix-title">
          <div className="section-heading compact">
            <span className="eyebrow">Folha mensal</span>
            <h2 id="payroll-matrix-title">Quais competências da folha estão publicadas</h2>
            <p>
              O calendário separa publicação, processamento pendente, conflito e
              documento não localizado sem presumir gasto zero.
            </p>
          </div>
          <FinancePayrollCoverageMatrix initialResult={payrollCoverage} />
        </section>

        <section className="finance-coverage-section" aria-labelledby="obligation-matrix-title">
          <div className="section-heading compact">
            <span className="eyebrow">Restos a pagar</span>
            <h2 id="obligation-matrix-title">O que foi encontrado em cada mês</h2>
            <p>
              A matriz informa se o balancete e a seção necessária foram validados;
              ela não representa o saldo da dívida municipal.
            </p>
          </div>
          <FinanceObligationCoverageMatrix initialResult={obligationCoverage} />
        </section>

        <section className="finance-coverage-section" aria-labelledby="municipal-document-coverage-title">
          <div className="section-heading compact">
            <span className="eyebrow">Documentos mensais</span>
            <h2 id="municipal-document-coverage-title">Balancete, receita e despesa por competência</h2>
            <p>
              As três famílias ficam lado a lado sem somar versões nem confundir
              arquivo catalogado com PDF efetivamente preservado.
            </p>
          </div>
          <FinanceMunicipalDocumentCoverage initialResult={municipalDocumentCoverage} />
        </section>

        <section className="finance-coverage-section" aria-labelledby="fiscal-report-coverage-title">
          <div className="section-heading compact">
            <span className="eyebrow">Calendário fiscal</span>
            <h2 id="fiscal-report-coverage-title">Quais RREO e RGF foram localizados</h2>
            <p>
              Seis RREO bimestrais e três RGF quadrimestrais são acompanhados por
              exercício, respeitando os prazos próprios de cada demonstrativo.
            </p>
          </div>
          <FinanceFiscalReportCoverageMatrix initialResult={fiscalCoverage} />
        </section>
      </section>
    </main>
  );
}
