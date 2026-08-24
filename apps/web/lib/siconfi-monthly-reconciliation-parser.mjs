const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const DECIMAL_ZERO = /^-?0(?:\.0{1,2})?$/;

export const SICONFI_RECONCILIATION_METRICS = Object.freeze([
  "expense_committed",
  "expense_liquidated",
  "expense_paid",
]);

export const SICONFI_RECONCILIATION_STATUSES = Object.freeze([
  "matched_exact",
  "source_difference",
  "incomplete_months",
]);

const METRICS = new Set(SICONFI_RECONCILIATION_METRICS);
const STATUSES = new Set(SICONFI_RECONCILIATION_STATUSES);

function decimal(value) {
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function parseRow(row) {
  if (
    !Number.isSafeInteger(row.fiscal_year) ||
    row.fiscal_year < 1988 ||
    row.fiscal_year > 2200 ||
    !METRICS.has(row.metric_key) ||
    !Number.isSafeInteger(row.observed_months) ||
    row.observed_months < 0 ||
    row.observed_months > 12 ||
    !Array.isArray(row.missing_months) ||
    !STATUSES.has(row.reconciliation_status) ||
    typeof row.reconciliation_note !== "string" ||
    !row.reconciliation_note.trim() ||
    row.methodology_version !== "siconfi-monthly-reconciliation/1.0.0"
  ) {
    return null;
  }

  const missingMonths = [...row.missing_months];
  if (
    missingMonths.some(
      (month) => !Number.isSafeInteger(month) || month < 1 || month > 12,
    ) ||
    new Set(missingMonths).size !== missingMonths.length ||
    missingMonths.some((month, index) => index > 0 && month <= missingMonths[index - 1])
  ) {
    return null;
  }

  const annualAmount = decimal(row.annual_amount);
  if (!annualAmount) return null;

  const complete = row.observed_months === 12;
  const monthlySumAmount = decimal(row.monthly_sum_amount);
  const differenceAmount = decimal(row.difference_amount);
  if (
    (complete && missingMonths.length !== 0) ||
    (!complete && missingMonths.length !== 12 - row.observed_months) ||
    (complete && (!monthlySumAmount || !differenceAmount)) ||
    (!complete && (row.monthly_sum_amount !== null || row.difference_amount !== null)) ||
    (row.reconciliation_status === "incomplete_months") !== !complete ||
    (row.reconciliation_status === "matched_exact" &&
      (!differenceAmount || !DECIMAL_ZERO.test(differenceAmount))) ||
    (row.reconciliation_status === "source_difference" &&
      differenceAmount !== null &&
      DECIMAL_ZERO.test(differenceAmount))
  ) {
    return null;
  }

  return {
    fiscalYear: row.fiscal_year,
    metricKey: row.metric_key,
    annualAmount,
    monthlySumAmount,
    differenceAmount,
    observedMonths: row.observed_months,
    missingMonths,
    reconciliationStatus: row.reconciliation_status,
    reconciliationNote: row.reconciliation_note.trim(),
    methodologyVersion: row.methodology_version,
  };
}

export function parseSiconfiMonthlyReconciliation(payload) {
  if (!Array.isArray(payload)) return null;
  const years = new Map();
  for (const rawRow of payload) {
    if (typeof rawRow !== "object" || rawRow === null) return null;
    const row = parseRow(rawRow);
    if (!row) return null;
    const metrics = years.get(row.fiscalYear) ?? new Map();
    if (metrics.has(row.metricKey)) return null;
    metrics.set(row.metricKey, row);
    years.set(row.fiscalYear, metrics);
  }

  const parsedYears = [];
  for (const [fiscalYear, metrics] of years) {
    if (metrics.size !== SICONFI_RECONCILIATION_METRICS.length) return null;
    const orderedMetrics = SICONFI_RECONCILIATION_METRICS.map((key) => metrics.get(key));
    if (orderedMetrics.some((metric) => !metric)) return null;
    parsedYears.push({ fiscalYear, metrics: orderedMetrics });
  }
  return parsedYears.sort((left, right) => right.fiscalYear - left.fiscalYear);
}
