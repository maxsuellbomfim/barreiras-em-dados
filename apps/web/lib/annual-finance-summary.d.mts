import type { PublicMonthlyFinanceClosure } from "./monthly-finance";

export type AnnualFinanceSummary = Readonly<{
  fiscalYear: number;
  comparableMonthCount: number;
  firstPeriodStart: string;
  lastPeriodStart: string;
  revenueAmount: string;
  paidAmount: string;
  operationalDifferenceAmount: string;
  isFullCalendarYear: boolean;
}>;

export function summarizeAnnualFinances(
  closures: readonly PublicMonthlyFinanceClosure[],
): readonly AnnualFinanceSummary[];
