const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const DECIMAL_ZERO = /^-?0(?:\.0{1,2})?$/;

const METRICS = new Set([
  "expense_committed",
  "expense_liquidated",
  "expense_paid",
]);
const STATUSES = new Set([
  "matched_exact",
  "source_difference",
  "incomplete_months",
]);

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
    missingMonths.some(
      (month, index) => index > 0 && month <= missingMonths[index - 1],
    )
  ) {
    return null;
  }

  const annualAmount = decimal(row.annual_amount);
  const monthlySumAmount = decimal(row.monthly_sum_amount);
  const differenceAmount = decimal(row.difference_amount);
  const complete = row.observed_months === 12;
  if (
    !annualAmount ||
    (complete && missingMonths.length !== 0) ||
    (!complete && missingMonths.length !== 12 - row.observed_months) ||
    (complete && (!monthlySumAmount || !differenceAmount)) ||
    (!complete &&
      (row.monthly_sum_amount !== null || row.difference_amount !== null)) ||
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

export function parseAdminSiconfiReconciliation(payload) {
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
    if (metrics.size !== METRICS.size) return null;
    const orderedMetrics = [
      "expense_committed",
      "expense_liquidated",
      "expense_paid",
    ].map((key) => metrics.get(key));
    if (orderedMetrics.some((metric) => !metric)) return null;
    parsedYears.push({ fiscalYear, metrics: orderedMetrics });
  }
  return parsedYears.sort((left, right) => right.fiscalYear - left.fiscalYear);
}

export function summarizeAdminSiconfiReconciliation(years) {
  const metrics = years.flatMap((year) => year.metrics);
  return {
    years: years.length,
    exactMatches: metrics.filter(
      (metric) => metric.reconciliationStatus === "matched_exact",
    ).length,
    sourceDifferences: metrics.filter(
      (metric) => metric.reconciliationStatus === "source_difference",
    ).length,
    incompleteMetrics: metrics.filter(
      (metric) => metric.reconciliationStatus === "incomplete_months",
    ).length,
  };
}
