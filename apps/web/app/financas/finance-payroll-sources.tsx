import type { PublicPayrollMonth } from "../../lib/public-payroll.mjs";

type PayrollSourceDocument = PublicPayrollMonth["sourceDocuments"][number];

const cycleLabels: Record<PayrollSourceDocument["payrollCycle"], string> = {
  regular: "Folha regular, complementar e rescisões",
  thirteenth_advance: "Adiantamento do 13º salário",
  thirteenth_final: "13º salário final",
};

const collectedAtFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatCollectedAt(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : collectedAtFormatter.format(parsed);
}

export default function FinancePayrollSources({
  documents,
}: Readonly<{ documents: readonly PayrollSourceDocument[] }>) {
  return (
    <ul className="finance-payroll-sources">
      {documents.map((document) => (
        <li key={`${document.payrollCycle}-${document.artifactSha256}`}>
          <strong>{cycleLabels[document.payrollCycle]}</strong>
          <span>
            <a href={document.sourceUrl} target="_blank" rel="noreferrer">
              Abrir PDF oficial →
            </a>{" "}
            · coletado em {formatCollectedAt(document.sourceRetrievedAt)} · hash{" "}
            {document.artifactSha256.slice(0, 12)}…
          </span>
        </li>
      ))}
    </ul>
  );
}
