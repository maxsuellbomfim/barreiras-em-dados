import type { PublicPayrollCoverageRow } from "../../lib/public-payroll.mjs";

function formatMonthTitle(value: string): string {
  const parsed = new Date(`${value}T12:00:00-03:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

function formatCheckedAt(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

function statusLabel(status: PublicPayrollCoverageRow["coverageStatus"]): string {
  if (status === "document_not_found") return "Não localizado no catálogo";
  if (status === "source_conflict") return "Documento com conflito";
  if (status === "processing_pending") return "Em validação";
  return "Publicado";
}

export default function FinancePayrollCoverage({
  rows,
}: Readonly<{ rows: readonly PublicPayrollCoverageRow[] }>) {
  const gaps = rows.filter((row) => row.coverageStatus !== "published");
  if (gaps.length === 0) return null;

  return (
    <details className="finance-payroll-coverage">
      <summary>
        <span>Ver competências sem total publicado</span>
        <small>
          {gaps.length.toLocaleString("pt-BR")} competência
          {gaps.length === 1 ? " explicada" : "s explicadas"}
        </small>
      </summary>
      <div className="finance-payroll-coverage-list">
        <p className="finance-payroll-coverage-intro">
          Isso não significa gasto zero. Cada lacuna abaixo informa o que foi
          encontrado no catálogo oficial e por que nenhum valor foi presumido.
        </p>
        {gaps.map((row) => (
          <article
            className={`finance-payroll-coverage-card finance-payroll-coverage-${row.coverageStatus}`}
            key={row.referenceMonth}
          >
            <header>
              <h3>{formatMonthTitle(row.referenceMonth)}</h3>
              <span>{statusLabel(row.coverageStatus)}</span>
            </header>
            <p>{row.coverageNote}</p>
            {row.coverageStatus === "source_conflict" ? (
              <p className="finance-payroll-coverage-explainer">
                Quando o mesmo PDF mistura ciclos da folha, como folha regular
                e 13º, o portal preserva o documento, mas não soma valores que
                não podem ser separados com segurança.
              </p>
            ) : null}
            <footer>
              <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                Conferir fonte oficial ↗
              </a>
              <span>
                Catálogo conferido em {formatCheckedAt(row.catalogCheckedAt)}
              </span>
              {row.artifactSha256 ? (
                <span>hash {row.artifactSha256.slice(0, 12)}…</span>
              ) : null}
            </footer>
          </article>
        ))}
      </div>
    </details>
  );
}
