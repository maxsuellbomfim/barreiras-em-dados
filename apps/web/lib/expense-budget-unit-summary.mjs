const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const UNIT_CODE = /^\d{6,8}$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const METHODOLOGY = "public-expense-budget-unit-summary/1.0.0";
const STATUSES = new Set(["matched", "partial", "source_conflict", "amount_mismatch"]);

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

function decimalToCents(value) {
  const match = typeof value === "string" ? DECIMAL.exec(value) : null;
  if (!match) return null;
  const cents = BigInt(match[2]) * 100n + BigInt((match[3] ?? "").padEnd(2, "0"));
  return match[1] === "-" ? -cents : cents;
}

function parseRow(value, expectedReportId) {
  if (typeof value !== "object" || value === null) return null;
  const row = value;
  const expenseReportId = nonEmptyString(row.expense_report_id);
  const budgetUnitCode = nonEmptyString(row.budget_unit_code);
  const budgetUnitName = nonEmptyString(row.budget_unit_name);
  const committedPeriodAmount = decimal(row.committed_period_amount);
  const liquidatedPeriodAmount = decimal(row.liquidated_period_amount);
  const paidPeriodAmount = decimal(row.paid_period_amount);
  const reportTotalPaidAmount = decimal(row.report_total_paid_amount);
  const allocatedTotalPaidAmount = decimal(row.allocated_total_paid_amount);
  const reconciliationStatus = row.reconciliation_status;
  const paidSharePercent = decimal(row.paid_share_percent);
  const reportTotalCents = decimalToCents(reportTotalPaidAmount);

  if (
    expenseReportId !== expectedReportId ||
    budgetUnitCode === null ||
    !UNIT_CODE.test(budgetUnitCode) ||
    budgetUnitName === null ||
    !Number.isSafeInteger(row.budget_unit_name_count) ||
    row.budget_unit_name_count < 1 ||
    !Number.isSafeInteger(row.line_count) ||
    row.line_count < 1 ||
    row.budget_unit_name_count > row.line_count ||
    !Number.isSafeInteger(row.report_line_count) ||
    row.report_line_count < 1 ||
    !Number.isSafeInteger(row.allocated_line_count) ||
    row.allocated_line_count < 1 ||
    row.allocated_line_count > row.report_line_count ||
    committedPeriodAmount === null ||
    liquidatedPeriodAmount === null ||
    paidPeriodAmount === null ||
    reportTotalPaidAmount === null ||
    allocatedTotalPaidAmount === null ||
    !STATUSES.has(reconciliationStatus) ||
    (reconciliationStatus === "matched" &&
      reportTotalCents !== 0n && paidSharePercent === null) ||
    (reconciliationStatus === "matched" &&
      reportTotalCents === 0n && row.paid_share_percent !== null) ||
    (reconciliationStatus !== "matched" && row.paid_share_percent !== null) ||
    row.methodology_version !== METHODOLOGY
  ) {
    return null;
  }

  return {
    expenseReportId,
    budgetUnitCode,
    budgetUnitName,
    budgetUnitNameCount: row.budget_unit_name_count,
    lineCount: row.line_count,
    reportLineCount: row.report_line_count,
    allocatedLineCount: row.allocated_line_count,
    committedPeriodAmount,
    liquidatedPeriodAmount,
    paidPeriodAmount,
    reportTotalPaidAmount,
    allocatedTotalPaidAmount,
    reconciliationStatus,
    paidSharePercent,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseExpenseBudgetUnitSummaryRows(payload, expectedReportId) {
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
  const reportTotal = decimalToCents(first.reportTotalPaidAmount);
  const allocatedTotal = decimalToCents(first.allocatedTotalPaidAmount);
  if (
    reportTotal === null ||
    allocatedTotal === null ||
    rows.some(
      (row) =>
        decimalToCents(row.reportTotalPaidAmount) !== reportTotal ||
        decimalToCents(row.allocatedTotalPaidAmount) !== allocatedTotal ||
        row.reportLineCount !== first.reportLineCount ||
        row.allocatedLineCount !== first.allocatedLineCount,
    )
  ) {
    return { state: "unavailable" };
  }

  const conflict = rows.find((row) => row.reconciliationStatus !== "matched");
  if (conflict) {
    return {
      state: "conflict",
      reason: conflict.reconciliationStatus,
      reportLineCount: first.reportLineCount,
      allocatedLineCount: first.allocatedLineCount,
    };
  }
  if (allocatedTotal !== reportTotal) return { state: "unavailable" };

  return {
    state: "available",
    budgetUnits: rows.map(({ reconciliationStatus: _status, ...unit }) => unit),
  };
}

export async function getPublicExpenseBudgetUnitSummary(reportId) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !UUID.test(reportId) ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_expense_budget_unit_summary`,
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
    return parseExpenseBudgetUnitSummaryRows(await response.json(), reportId);
  } catch {
    return { state: "unavailable" };
  }
}
