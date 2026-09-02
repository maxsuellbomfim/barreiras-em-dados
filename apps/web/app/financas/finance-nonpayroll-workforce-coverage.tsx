import type {
  PublicNonpayrollWorkforceCoverageRow,
} from "../../lib/public-payroll.mjs";

const NONPAYROLL_OVERVIEW_LIMIT = 12;

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

function statusLabel(
  status: PublicNonpayrollWorkforceCoverageRow["coverageStatus"],
): string {
  if (status === "document_preserved") {
    return "PDF preservado; total em validação";
  }
  if (status === "catalogued") return "Listado; PDF ainda não preservado";
  return "Não listado no catálogo do mês";
}

export default function FinanceNonpayrollWorkforceCoverage({
  rows,
}: Readonly<{ rows: readonly PublicNonpayrollWorkforceCoverageRow[] }>) {
  if (rows.length === 0) return null;
  const documentedRows = rows
    .filter((row) => row.coverageStatus !== "not_listed")
    .sort((left, right) => right.referenceMonth.localeCompare(left.referenceMonth));
  const recentDocumentedRows = documentedRows.slice(0, NONPAYROLL_OVERVIEW_LIMIT);
  const notListedCount = rows.length - documentedRows.length;

  return (
    <details className="finance-payroll-coverage">
      <summary>
        <span>Estagiários e terceirizados: acompanhamento separado</span>
        <small>
          {recentDocumentedRows.length.toLocaleString("pt-BR")} registro
          {recentDocumentedRows.length === 1 ? " recente" : "s recentes"} de{" "}
          {documentedRows.length.toLocaleString("pt-BR")} documentado
          {documentedRows.length === 1 ? "" : "s"}
        </small>
      </summary>
      <div className="finance-payroll-coverage-list">
        <p className="finance-payroll-coverage-intro">
          Estagiários e terceirizados não entram no total da folha regular. Os
          relatórios oficiais podem conter CPF e dados bancários; por isso,
          nenhum valor agregado é presumido. O portal só mostrará totais quando
          as colunas e o total declarado fecharem deterministicamente.
        </p>
        {recentDocumentedRows.map((row) => (
          <article
            className="finance-payroll-coverage-card"
            key={`${row.referenceMonth}-${row.workforceCategory}`}
          >
            <header>
              <h3>
                {row.categoryLabel} · {formatMonthTitle(row.referenceMonth)}
              </h3>
              <span>{statusLabel(row.coverageStatus)}</span>
            </header>
            <p>{row.coverageNote}</p>
            <footer>
              <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                Conferir catálogo oficial ↗
              </a>
              <span>
                {row.catalogDocumentCount.toLocaleString("pt-BR")} documento
                {row.catalogDocumentCount === 1 ? " listado" : "s listados"};{" "}
                {row.preservedDocumentCount.toLocaleString("pt-BR")} preservado
                {row.preservedDocumentCount === 1 ? "" : "s"}
              </span>
              <span>
                Catálogo conferido em {formatCheckedAt(row.catalogCheckedAt)}
              </span>
              {row.artifactSha256 ? (
                <span>hash {row.artifactSha256.slice(0, 12)}…</span>
              ) : null}
            </footer>
          </article>
        ))}
        {notListedCount > 0 ? (
          <p className="finance-payroll-coverage-intro">
            Em {notListedCount.toLocaleString("pt-BR")} combinações de mês e
            categoria, o catálogo oficial completo não listou documento. Isso
            não significa ausência de pessoas, serviço ou gasto.
          </p>
        ) : null}
      </div>
    </details>
  );
}
