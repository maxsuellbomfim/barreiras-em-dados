const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const METHODOLOGY = "public-expense-category-summary/1.0.0";

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value.trim())) {
    return value.trim();
  }
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Math.abs(value) <= Number.MAX_SAFE_INTEGER
  ) {
    const serialized = String(value);
    return DECIMAL.test(serialized) ? serialized : null;
  }
  return null;
}

function parseRow(value, expectedReportId) {
  if (typeof value !== "object" || value === null) return null;
  const row = value;
  const expenseReportId = nonEmptyString(row.expense_report_id);
  const expenseCode = nonEmptyString(row.expense_code);
  const sourceDescription = nonEmptyString(row.source_description);
  const committedPeriodAmount = decimal(row.committed_period_amount);
  const liquidatedPeriodAmount = decimal(row.liquidated_period_amount);
  const paidPeriodAmount = decimal(row.paid_period_amount);
  const reportTotalPaidAmount = decimal(row.report_total_paid_amount);
  const aggregatedTotalPaidAmount = decimal(row.aggregated_total_paid_amount);
  const reconciliationStatus = row.reconciliation_status;
  const paidSharePercent = decimal(row.paid_share_percent);

  if (
    expenseReportId !== expectedReportId ||
    expenseCode === null ||
    sourceDescription === null ||
    !Number.isSafeInteger(row.source_description_count) ||
    row.source_description_count < 1 ||
    !Number.isSafeInteger(row.line_count) ||
    row.line_count < 1 ||
    row.source_description_count > row.line_count ||
    committedPeriodAmount === null ||
    liquidatedPeriodAmount === null ||
    paidPeriodAmount === null ||
    reportTotalPaidAmount === null ||
    aggregatedTotalPaidAmount === null ||
    !["matched", "mismatch"].includes(reconciliationStatus) ||
    (reconciliationStatus === "matched" && paidSharePercent === null) ||
    (reconciliationStatus === "mismatch" && row.paid_share_percent !== null) ||
    row.methodology_version !== METHODOLOGY
  ) {
    return null;
  }

  return {
    expenseReportId,
    expenseCode,
    sourceDescription,
    sourceDescriptionCount: row.source_description_count,
    lineCount: row.line_count,
    committedPeriodAmount,
    liquidatedPeriodAmount,
    paidPeriodAmount,
    reportTotalPaidAmount,
    aggregatedTotalPaidAmount,
    reconciliationStatus,
    paidSharePercent,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseExpenseCategorySummaryRows(payload, expectedReportId) {
  if (!UUID.test(expectedReportId) || !Array.isArray(payload)) {
    return { state: "unavailable" };
  }
  if (payload.length === 0) return { state: "empty" };

  const rows = [];
  for (const value of payload) {
    const parsed = parseRow(value, expectedReportId);
    if (parsed === null) return { state: "unavailable" };
    rows.push(parsed);
  }

  const first = rows[0];
  if (
    rows.some(
      (row) =>
        row.reportTotalPaidAmount !== first.reportTotalPaidAmount ||
        row.aggregatedTotalPaidAmount !== first.aggregatedTotalPaidAmount ||
        row.reconciliationStatus !== first.reconciliationStatus,
    )
  ) {
    return { state: "unavailable" };
  }

  if (first.reconciliationStatus === "mismatch") {
    return {
      state: "conflict",
      reportTotalPaidAmount: first.reportTotalPaidAmount,
      aggregatedTotalPaidAmount: first.aggregatedTotalPaidAmount,
    };
  }

  return {
    state: "available",
    categories: rows.map(({ reconciliationStatus: _status, ...category }) => category),
  };
}

export async function getPublicExpenseCategorySummary(reportId) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !UUID.test(reportId) ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_expense_category_summary`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ report_filter: reportId }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    return parseExpenseCategorySummaryRows(await response.json(), reportId);
  } catch {
    return { state: "unavailable" };
  }
}
