import type {
  PublicPayrollCompensationRow,
  PublicPayrollMonth,
  PublicPayrollRegimeRow,
} from "../../lib/public-payroll.mjs";
import { payrollDocumentNotes } from "../../lib/payroll-document-notes.mjs";
import { formatBrlDecimal } from "../../lib/revenues";
import FinancePayrollCompensation from "./finance-payroll-compensation";
import FinancePayrollRegimeBreakdown from "./finance-payroll-regime-breakdown";
import FinancePayrollSources from "./finance-payroll-sources";

export function formatPayrollMonthTitle(value: string): string {
  const parsed = new Date(`${value}T12:00:00-03:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

// Cartão de uma competência da folha: totais, divisão por vínculo, faixas de
// provento e documentos. Usado no destaque de /financas e em
// /financas/folha/AAAA-MM, para que todo mês publicado tenha a mesma leitura.
export default function FinancePayrollMonthCard({
  month,
  regimeRows,
  compensationRows,
}: Readonly<{
  month: PublicPayrollMonth;
  regimeRows: readonly PublicPayrollRegimeRow[];
  compensationRows: readonly PublicPayrollCompensationRow[];
}>) {
  const notes = payrollDocumentNotes(month.sourceDocuments);
  return (
    <article className="finance-payroll-card">
      <div className="finance-payroll-header">
        <div>
          <span className="finance-payroll-kicker">{month.publicBodyName}</span>
          <h3>{formatPayrollMonthTitle(month.referenceMonth)}</h3>
          <p>
            A folha regular informa{" "}
            <strong>{month.employeeCount.toLocaleString("pt-BR")} vínculos</strong>
            . Um vínculo não representa necessariamente uma pessoa única.
          </p>
        </div>
        <span className="finance-payroll-status">
          {month.documentCount.toLocaleString("pt-BR")} PDF
          {month.documentCount === 1 ? "" : "s"} reconciliado
          {month.documentCount === 1 ? "" : "s"}
        </span>
      </div>
      {notes.map((note) => (
        <aside className="finance-payroll-document-note" key={note.title}>
          <strong>{note.title}</strong>
          <p>{note.body}</p>
        </aside>
      ))}
      <dl className="finance-payroll-values">
        <div className="finance-payroll-gross">
          <dt>
            Proventos brutos do mês
            <small>Soma dos processamentos oficiais publicados</small>
          </dt>
          <dd>{formatBrlDecimal(month.grossAmount)}</dd>
        </div>
        <div>
          <dt>
            Descontos
            <small>Retenções consolidadas, sem detalhe pessoal</small>
          </dt>
          <dd>{formatBrlDecimal(month.deductionAmount)}</dd>
        </div>
        <div className="finance-payroll-net">
          <dt>
            Líquido nos relatórios
            <small>Bruto menos descontos; não é confirmação bancária</small>
          </dt>
          <dd>{formatBrlDecimal(month.netAmount)}</dd>
        </div>
      </dl>
      <div className="finance-payroll-reading">
        <strong>Como ler este mês</strong>
        <p>
          O total reúne {month.documentCount.toLocaleString("pt-BR")}{" "}
          {month.documentCount === 1
            ? "processamento oficial"
            : "processamentos oficiais"}
          : {formatBrlDecimal(month.grossAmount)} brutos,{" "}
          {formatBrlDecimal(month.deductionAmount)} em descontos e{" "}
          {formatBrlDecimal(month.netAmount)} líquidos. O código conferiu{" "}
          {month.subtotalCount.toLocaleString("pt-BR")} subtotais sem somar os
          vínculos repetidos no 13º.
        </p>
      </div>
      <FinancePayrollRegimeBreakdown
        rows={regimeRows}
        grossTotal={month.grossAmount}
      />
      <FinancePayrollCompensation rows={compensationRows} />
      <details className="finance-details">
        <summary>Conferir cálculo, fonte e documento</summary>
        <p className="finance-details-note">
          Regra determinística: proventos brutos − descontos = líquido. O
          Barreiras 360 não usa IA para calcular esses valores.
        </p>
        <FinancePayrollSources documents={month.sourceDocuments} />
        <p className="finance-details-note">
          Projeção mensal {month.parserVersion}. Cada documento mantém hash e
          data de coleta próprios.
        </p>
      </details>
    </article>
  );
}
