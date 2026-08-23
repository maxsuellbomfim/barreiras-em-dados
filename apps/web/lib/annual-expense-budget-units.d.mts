import type { ExpenseBudgetUnitSummaryResult } from "./expense-budget-unit-summary.mjs";
import type { PublicExpenseReport } from "./expenses";
import type { PublicMonthlyFinanceClosure } from "./monthly-finance";

export type AnnualExpenseBudgetUnitMonth = Readonly<{
  periodStart: string;
  paidAmount: string | null;
  barBasisPoints: number | null;
  documentSourceUrl: string | null;
  documentArtifactSha256: string | null;
}>;

export type AnnualExpenseBudgetUnit = Readonly<{
  budgetUnitCode: string;
  budgetUnitName: string;
  lineCount: number;
  monthCount: number;
  paidAmount: string;
  paidSharePercent: string | null;
  months: readonly AnnualExpenseBudgetUnitMonth[];
}>;

export type AnnualExpenseBudgetUnitsResult =
  | Readonly<{
      state: "available";
      fiscalYear: number;
      comparableMonthCount: number;
      unitCoveredMonthCount: number;
      annualPaidAmount: string;
      budgetUnits: readonly AnnualExpenseBudgetUnit[];
    }>
  | Readonly<{ state: "empty"; comparableMonthCount: number; unitCoveredMonthCount: 0 }>
  | Readonly<{
      state: "conflict";
      periodStart: string;
      reason: "expense_total_mismatch" | "unit_total_mismatch" | "unit_name_conflict";
    }>
  | Readonly<{ state: "unavailable" }>;

export function buildAnnualExpenseBudgetUnits(input: Readonly<{
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
  summariesByReport: ReadonlyMap<string, ExpenseBudgetUnitSummaryResult>;
}>): AnnualExpenseBudgetUnitsResult;
