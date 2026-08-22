import type { ExpenseCategorySummaryResult } from "./expense-category-summary.mjs";

export type ExpenseCategoryMonthComparison =
  | Readonly<{
      state: "available";
      currentTotalPaidAmount: string;
      previousTotalPaidAmount: string;
      totalDifferenceAmount: string;
      categories: readonly Readonly<{
        expenseCode: string;
        sourceDescription: string;
        currentPaidAmount: string;
        previousPaidAmount: string | null;
        differenceAmount: string | null;
      }>[];
    }>
  | Readonly<{ state: "unavailable" }>;

export function previousMonthStart(periodStart: string): string | null;

export function compareExpenseCategoryMonths(
  current: ExpenseCategorySummaryResult,
  previous: ExpenseCategorySummaryResult,
): ExpenseCategoryMonthComparison;
