import type { PublicExpenseReport } from "./expenses";
import type { ExpenseCategorySummaryResult } from "./expense-category-summary.mjs";
import type { PublicMonthlyFinanceClosure } from "./monthly-finance";

export type AnnualExpenseCategoryMonth = Readonly<{
  periodStart: string;
  paidAmount: string | null;
  barBasisPoints: number | null;
  documentSourceUrl: string | null;
  documentArtifactSha256: string | null;
}>;

export type AnnualExpenseCategory = Readonly<{
  expenseCode: string;
  sourceDescription: string;
  descriptionVariationObserved: boolean;
  lineCount: number;
  monthCount: number;
  paidAmount: string;
  paidSharePercent: string | null;
  months: readonly AnnualExpenseCategoryMonth[];
}>;

export type AnnualExpenseCategoriesResult =
  | Readonly<{
      state: "available";
      fiscalYear: number;
      comparableMonthCount: number;
      categoryCoveredMonthCount: number;
      annualPaidAmount: string;
      categories: readonly AnnualExpenseCategory[];
    }>
  | Readonly<{
      state: "empty";
      comparableMonthCount: number;
      categoryCoveredMonthCount: 0;
    }>
  | Readonly<{
      state: "conflict";
      periodStart: string;
      reason: "expense_total_mismatch" | "category_total_mismatch";
    }>
  | Readonly<{ state: "unavailable" }>;

export function buildAnnualExpenseCategories(input: Readonly<{
  fiscalYear: number;
  closures: readonly Pick<
    PublicMonthlyFinanceClosure,
    "fiscalYear" | "periodStart" | "closureStatus" | "expensePaidAmount"
  >[];
  reports: readonly Pick<
    PublicExpenseReport,
    | "expenseReportId"
    | "fiscalYear"
    | "periodStart"
    | "totalPaidPeriodAmount"
    | "documentSourceUrl"
    | "documentArtifactSha256"
  >[];
  summariesByReport: ReadonlyMap<string, ExpenseCategorySummaryResult>;
}>): AnnualExpenseCategoriesResult;
