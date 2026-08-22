export type PublicExpenseCategory = Readonly<{
  expenseReportId: string;
  expenseCode: string;
  sourceDescription: string;
  sourceDescriptionCount: number;
  lineCount: number;
  committedPeriodAmount: string;
  liquidatedPeriodAmount: string;
  paidPeriodAmount: string;
  reportTotalPaidAmount: string;
  aggregatedTotalPaidAmount: string;
  paidSharePercent: string;
  methodologyVersion: "public-expense-category-summary/1.0.0";
}>;

export type ExpenseCategorySummaryResult =
  | Readonly<{ state: "available"; categories: readonly PublicExpenseCategory[] }>
  | Readonly<{ state: "empty" }>
  | Readonly<{
      state: "conflict";
      reportTotalPaidAmount: string;
      aggregatedTotalPaidAmount: string;
    }>
  | Readonly<{ state: "unavailable" }>;

export function parseExpenseCategorySummaryRows(
  payload: unknown,
  expectedReportId: string,
): ExpenseCategorySummaryResult;

export function getPublicExpenseCategorySummary(
  reportId: string,
): Promise<ExpenseCategorySummaryResult>;
