export type SiconfiReconciliationMetricKey =
  | "expense_committed"
  | "expense_liquidated"
  | "expense_paid";

export type SiconfiReconciliationStatus =
  | "matched_exact"
  | "source_difference"
  | "incomplete_months";

export type ParsedSiconfiReconciliationMetric = Readonly<{
  fiscalYear: number;
  metricKey: SiconfiReconciliationMetricKey;
  annualAmount: string;
  monthlySumAmount: string | null;
  differenceAmount: string | null;
  observedMonths: number;
  missingMonths: readonly number[];
  reconciliationStatus: SiconfiReconciliationStatus;
  reconciliationNote: string;
  methodologyVersion: "siconfi-monthly-reconciliation/1.0.0";
}>;

export type ParsedSiconfiReconciliationYear = Readonly<{
  fiscalYear: number;
  metrics: readonly ParsedSiconfiReconciliationMetric[];
}>;

export const SICONFI_RECONCILIATION_METRICS: readonly SiconfiReconciliationMetricKey[];
export const SICONFI_RECONCILIATION_STATUSES: readonly SiconfiReconciliationStatus[];
export function parseSiconfiMonthlyReconciliation(
  payload: unknown,
): ParsedSiconfiReconciliationYear[] | null;
