import type { PublicMonthlyFinanceClosure } from "./monthly-finance";

export type AnnualFinanceTrendMonth = Readonly<{
  month: number;
  periodStart: string;
  closureStatus: PublicMonthlyFinanceClosure["closureStatus"] | "missing";
  revenueAmount: string | null;
  paidAmount: string | null;
  operationalDifferenceAmount: string | null;
  revenueBarBasisPoints: number | null;
  paidBarBasisPoints: number | null;
}>;

export type AnnualFinanceTrend =
  | Readonly<{
      state: "available";
      comparableMonthCount: number;
      months: readonly AnnualFinanceTrendMonth[];
    }>
  | Readonly<{ state: "unavailable" }>;

export function buildAnnualFinanceTrend(
  closures: readonly PublicMonthlyFinanceClosure[],
  fiscalYear: number,
): AnnualFinanceTrend;

export function parseFinanceYearSlug(
  value: string,
  currentYear: number,
): number | null;
