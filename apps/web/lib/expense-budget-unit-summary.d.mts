export type PublicExpenseBudgetUnit = Readonly<{
  expenseReportId: string;
  budgetUnitCode: string;
  budgetUnitName: string;
  budgetUnitNameCount: number;
  lineCount: number;
  reportLineCount: number;
  allocatedLineCount: number;
  committedPeriodAmount: string;
  liquidatedPeriodAmount: string;
  paidPeriodAmount: string;
  reportTotalPaidAmount: string;
  allocatedTotalPaidAmount: string;
  paidSharePercent: string | null;
  methodologyVersion: "public-expense-budget-unit-summary/1.0.0";
}>;

export type ExpenseBudgetUnitSummaryResult =
  | Readonly<{
      state: "available";
      budgetUnits: readonly PublicExpenseBudgetUnit[];
    }>
  | Readonly<{ state: "empty" }>
  | Readonly<{
      state: "conflict";
      reason: "partial" | "source_conflict" | "amount_mismatch";
      reportLineCount: number;
      allocatedLineCount: number;
    }>
  | Readonly<{ state: "unavailable" }>;

export function parseExpenseBudgetUnitSummaryRows(
  payload: unknown,
  expectedReportId: string,
): ExpenseBudgetUnitSummaryResult;

export function getPublicExpenseBudgetUnitSummary(
  reportId: string,
): Promise<ExpenseBudgetUnitSummaryResult>;
