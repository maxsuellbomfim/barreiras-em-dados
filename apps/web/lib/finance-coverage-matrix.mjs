const COVERAGE_STATUSES = new Set([
  "complete",
  "needs_review",
  "revenue_only",
  "expense_only",
  "missing",
]);

const PERIOD_START = /^(\d{4})-(\d{2})-01$/;

export function financeCoverageStatusLabel(status) {
  if (status === "complete") return "Receita e despesa";
  if (status === "revenue_only") return "Só receita";
  if (status === "expense_only") return "Só despesa";
  if (status === "needs_review") return "Revisão necessária";
  if (status === "missing") return "Sem relatório validado";
  if (status === "unclassified") return "Não classificado";
  return "Fora do período acompanhado";
}

function parsePeriod(row, startYear) {
  const match = PERIOD_START.exec(row.periodStart);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (
    year < startYear ||
    month < 1 ||
    month > 12 ||
    row.fiscalYear !== year ||
    !COVERAGE_STATUSES.has(row.coverageStatus) ||
    !row.publicBodyName.trim()
  ) return null;
  return { year, month, key: `${year}-${String(month).padStart(2, "0")}` };
}

export function buildFinanceCoverageMatrix(rows, startYear = 2021) {
  if (!Number.isInteger(startYear) || startYear < 1900 || startYear > 2200) return null;
  if (rows.length === 0) return { latestPeriod: null, bodies: [] };

  const byBody = new Map();
  let latestPeriod = null;

  for (const row of rows) {
    const period = parsePeriod(row, startYear);
    if (!period) return null;
    const bodyRows = byBody.get(row.publicBodyName) ?? new Map();
    if (bodyRows.has(period.key)) return null;
    bodyRows.set(period.key, row);
    byBody.set(row.publicBodyName, bodyRows);
    if (latestPeriod === null || period.key > latestPeriod) latestPeriod = period.key;
  }

  if (latestPeriod === null) return { latestPeriod: null, bodies: [] };
  const latestYear = Number(latestPeriod.slice(0, 4));
  const latestMonth = Number(latestPeriod.slice(5, 7));
  const bodies = [...byBody.entries()]
    .sort(([left], [right]) => left.localeCompare(right, "pt-BR"))
    .map(([publicBodyName, bodyRows]) => ({
      publicBodyName,
      years: Array.from({ length: latestYear - startYear + 1 }, (_, yearIndex) => {
        const year = latestYear - yearIndex;
        return {
          year,
          months: Array.from({ length: 12 }, (_, monthIndex) => {
            const month = monthIndex + 1;
            const afterLatest = year === latestYear && month > latestMonth;
            const key = `${year}-${String(month).padStart(2, "0")}`;
            const row = bodyRows.get(key) ?? null;
            return {
              month,
              status: afterLatest ? "not_due" : row?.coverageStatus ?? "unclassified",
              row,
            };
          }),
        };
      }),
    }));

  return { latestPeriod, bodies };
}
