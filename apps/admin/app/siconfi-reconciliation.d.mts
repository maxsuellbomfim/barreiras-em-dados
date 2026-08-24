export type AdminSiconfiReconciliationMetricKey =
  | "expense_committed"
  | "expense_liquidated"
  | "expense_paid";

export type AdminSiconfiReconciliationStatus =
  | "matched_exact"
  | "source_difference"
  | "incomplete_months";

export type AdminSiconfiReconciliationMetric = Readonly<{
  fiscalYear: number;
  metricKey: AdminSiconfiReconciliationMetricKey;
  annualAmount: string;
  monthlySumAmount: string | null;
  differenceAmount: string | null;
  observedMonths: number;
  missingMonths: readonly number[];
  reconciliationStatus: AdminSiconfiReconciliationStatus;
  reconciliationNote: string;
  methodologyVersion: "siconfi-monthly-reconciliation/1.0.0";
}>;

export type AdminSiconfiReconciliationYear = Readonly<{
  fiscalYear: number;
  metrics: readonly AdminSiconfiReconciliationMetric[];
}>;

export type AdminSiconfiReconciliationSummary = Readonly<{
  years: number;
  exactMatches: number;
  sourceDifferences: number;
  incompleteMetrics: number;
}>;

export function parseAdminSiconfiReconciliation(
  payload: unknown,
): AdminSiconfiReconciliationYear[] | null;

export function summarizeAdminSiconfiReconciliation(
  years: readonly AdminSiconfiReconciliationYear[],
): AdminSiconfiReconciliationSummary;
