import type {
  ExpenseReportSourceConflictsResult,
  PublicExpenseReportSourceConflict,
} from "../../../../lib/expense-report-source-conflicts.mjs";
import { formatBrlDecimal } from "../../../../lib/revenues";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatPeriod(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function absoluteDecimal(value: string): string {
  return value.startsWith("-") ? value.slice(1) : value;
}

function SourceConflict({ conflict }: Readonly<{
  conflict: PublicExpenseReportSourceConflict;
}>) {
  return (
    <li>
      <strong>{formatPeriod(conflict.periodStart)} · {conflict.fieldLabel}</strong>
      <p>
        O “Total” impresso no balancete informa {formatBrlDecimal(conflict.declaredAmount)}.
        A soma das linhas, conferida contra os subtotais oficiais de cada unidade,
        resulta em {formatBrlDecimal(conflict.calculatedAmount)}. A diferença existente
        no próprio documento é de {formatBrlDecimal(absoluteDecimal(conflict.differenceAmount))}.
      </p>
      <p>
        Essa diferença não foi corrigida, estimada ou escondida pelo Barreiras 360 e,
        isoladamente, não prova irregularidade. Os outros campos que fecharam
        aritmeticamente continuam disponíveis.
      </p>
      <a href={conflict.documentSourceUrl} target="_blank" rel="noreferrer">
        Conferir o balancete oficial →
      </a>{" "}
      <small>· hash {conflict.documentArtifactSha256.slice(0, 12)}…</small>
    </li>
  );
}

export function FinanceAnnualSourceConflicts({ result }: Readonly<{
  result: ExpenseReportSourceConflictsResult;
}>) {
  if (result.state !== "available" || result.conflicts.length === 0) return null;
  return (
    <section className="finance-year-source-conflicts" aria-labelledby="finance-source-conflicts-title">
      <div className="section-heading compact">
        <span className="eyebrow">Transparência da própria fonte</span>
        <h2 id="finance-source-conflicts-title">O balancete oficial contém uma diferença</h2>
        <p>
          Encontramos uma conta que não fecha dentro do documento publicado pela
          Prefeitura. Exibimos os dois valores exatamente como foram verificados.
        </p>
      </div>
      <ol>
        {result.conflicts.map((conflict) => (
          <SourceConflict
            key={`${conflict.expenseReportId}:${conflict.fieldName}`}
            conflict={conflict}
          />
        ))}
      </ol>
    </section>
  );
}
