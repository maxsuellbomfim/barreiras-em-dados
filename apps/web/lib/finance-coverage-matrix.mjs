const COVERAGE_STATUSES = new Set([
  "complete",
  "needs_review",
  "revenue_only",
  "expense_only",
  "missing",
]);

const PERIOD_START = /^(\d{4})-(\d{2})-01$/;
const PERIOD_KEY = /^(\d{4})-(\d{2})$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const COVERAGE_ROW_KEYS = new Set([
  "coverageId",
  "fiscalYear",
  "periodStart",
  "periodEnd",
  "publicBodyName",
  "revenueReportCount",
  "expenseReportCount",
  "coverageStatus",
  "coverageNote",
  "calculationMethodology",
]);

export function financeCoverageStatusLabel(status) {
  if (status === "complete") return "Receita e despesa";
  if (status === "revenue_only") return "Só receita";
  if (status === "expense_only") return "Só despesa";
  if (status === "needs_review") return "Revisão necessária";
  if (status === "missing") return "Sem relatório validado";
  if (status === "unclassified") return "Não classificado";
  return "Competência em andamento ou futura";
}

function parsePeriod(row, startYear) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  if (
    Object.keys(row).length !== COVERAGE_ROW_KEYS.size ||
    Object.keys(row).some((key) => !COVERAGE_ROW_KEYS.has(key)) ||
    typeof row.coverageId !== "string" ||
    !row.coverageId.trim() ||
    typeof row.periodStart !== "string" ||
    typeof row.periodEnd !== "string" ||
    !ISO_DATE.test(row.periodEnd) ||
    typeof row.publicBodyName !== "string" ||
    typeof row.coverageNote !== "string" ||
    !row.coverageNote.trim() ||
    row.calculationMethodology !== "finance-coverage/1.1.0" ||
    !Number.isSafeInteger(row.revenueReportCount) ||
    row.revenueReportCount < 0 ||
    !Number.isSafeInteger(row.expenseReportCount) ||
    row.expenseReportCount < 0
  ) return null;
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
  if (
    (row.coverageStatus === "complete" &&
      (row.revenueReportCount < 1 || row.expenseReportCount < 1)) ||
    (row.coverageStatus === "revenue_only" &&
      (row.revenueReportCount < 1 || row.expenseReportCount !== 0)) ||
    (row.coverageStatus === "expense_only" &&
      (row.revenueReportCount !== 0 || row.expenseReportCount < 1)) ||
    (row.coverageStatus === "needs_review" &&
      row.revenueReportCount <= 1 && row.expenseReportCount <= 1) ||
    (row.coverageStatus === "missing" &&
      (row.revenueReportCount !== 0 || row.expenseReportCount !== 0))
  ) return null;
  return { year, month, key: `${year}-${String(month).padStart(2, "0")}` };
}

export function parseFinanceCoverageApiPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.state === "unavailable") {
    return Object.keys(payload).length === 1 ? { state: "unavailable" } : null;
  }
  if (
    payload.state !== "available" ||
    Object.keys(payload).length !== 2 ||
    !Array.isArray(payload.rows) ||
    buildFinanceCoverageMatrix(payload.rows) === null
  ) return null;
  return { state: "available", rows: payload.rows };
}

export function buildFinanceCoverageMatrix(
  rows,
  startYear = 2021,
  currentPeriod = null,
) {
  if (!Number.isInteger(startYear) || startYear < 1900 || startYear > 2200) return null;
  if (currentPeriod !== null && !PERIOD_KEY.test(currentPeriod)) return null;
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
            const currentOrFutureWithoutReports =
              currentPeriod !== null &&
              key >= currentPeriod &&
              row?.coverageStatus === "missing";
            return {
              month,
              status: afterLatest || currentOrFutureWithoutReports
                ? "not_due"
                : row?.coverageStatus ?? "unclassified",
              row,
            };
          }),
        };
      }),
    }));

  return { latestPeriod, bodies };
}
