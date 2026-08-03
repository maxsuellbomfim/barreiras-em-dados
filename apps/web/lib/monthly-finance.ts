export type PublicMonthlyFinanceClosure = Readonly<{
  closureId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  publicBodyName: string;
  revenueReportAmount: string | null;
  revenueReportCount: number;
  revenueLineCount: number;
  expensePaidAmount: string | null;
  expenseCommittedAmount: string | null;
  expenseLiquidatedAmount: string | null;
  expenseReportCount: number;
  operationalDifferenceAmount: string | null;
  closureStatus: "operational" | "needs_data" | "needs_review";
  coverageNote: string;
  calculationMethodology: "monthly-finance-closure/1.0.0";
}>;

export type MonthlyFinanceResult =
  | Readonly<{
      state: "available";
      closures: readonly PublicMonthlyFinanceClosure[];
    }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function decimal(value: unknown): string | null {
  if (typeof value === "string" && DECIMAL.test(value.trim())) return value.trim();
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Math.abs(value) <= Number.MAX_SAFE_INTEGER
  ) {
    const normalized = String(value);
    return DECIMAL.test(normalized) ? normalized : null;
  }
  return null;
}

function integer(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function parseClosure(row: Record<string, unknown>): PublicMonthlyFinanceClosure | null {
  const closureId = text(row.closure_id);
  const periodStart = text(row.period_start);
  const periodEnd = text(row.period_end);
  const publicBodyName = text(row.public_body_name);
  const coverageNote = text(row.coverage_note);
  const methodology = row.calculation_methodology;
  const status = row.closure_status;
  const fiscalYear = row.fiscal_year;
  const revenueReportCount = integer(row.revenue_report_count);
  const revenueLineCount = integer(row.revenue_line_count);
  const expenseReportCount = integer(row.expense_report_count);
  if (
    !closureId ||
    !periodStart ||
    !ISO_DATE.test(periodStart) ||
    !periodEnd ||
    !ISO_DATE.test(periodEnd) ||
    !publicBodyName ||
    !coverageNote ||
    methodology !== "monthly-finance-closure/1.0.0" ||
    (status !== "operational" && status !== "needs_data" && status !== "needs_review") ||
    !Number.isSafeInteger(fiscalYear) ||
    revenueReportCount === null ||
    revenueLineCount === null ||
    expenseReportCount === null
  ) {
    return null;
  }
  const revenueReportAmount = decimal(row.revenue_report_amount);
  const expensePaidAmount = decimal(row.expense_paid_amount);
  const expenseCommittedAmount = decimal(row.expense_committed_amount);
  const expenseLiquidatedAmount = decimal(row.expense_liquidated_amount);
  const operationalDifferenceAmount = decimal(row.operational_difference_amount);
  if (
    (row.revenue_report_amount !== null && revenueReportAmount === null) ||
    (row.expense_paid_amount !== null && expensePaidAmount === null) ||
    (row.expense_committed_amount !== null && expenseCommittedAmount === null) ||
    (row.expense_liquidated_amount !== null && expenseLiquidatedAmount === null) ||
    (row.operational_difference_amount !== null && operationalDifferenceAmount === null)
  ) {
    return null;
  }
  return {
    closureId,
    fiscalYear: Number(fiscalYear),
    periodStart,
    periodEnd,
    publicBodyName,
    revenueReportAmount,
    revenueReportCount,
    revenueLineCount,
    expensePaidAmount,
    expenseCommittedAmount,
    expenseLiquidatedAmount,
    expenseReportCount,
    operationalDifferenceAmount,
    closureStatus: status,
    coverageNote,
    calculationMethodology: "monthly-finance-closure/1.0.0",
  };
}

export async function getPublicMonthlyFinanceClosures(
  fiscalYear?: number,
): Promise<MonthlyFinanceResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_monthly_finance_closures`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        page_size: 24,
        fiscal_year_filter: fiscalYear ?? null,
      }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const closures: PublicMonthlyFinanceClosure[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) return { state: "unavailable" };
      const closure = parseClosure(row as Record<string, unknown>);
      if (!closure) return { state: "unavailable" };
      closures.push(closure);
    }
    return { state: "available", closures };
  } catch {
    return { state: "unavailable" };
  }
}
