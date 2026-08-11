export type FinanceIntegrityStatus =
  | "ready"
  | "needs_data"
  | "needs_review"
  | "blocked";

export type FinanceIntegritySummaryItem = Readonly<{
  diagnostic_status: FinanceIntegrityStatus;
  revenue_reconciled_count: number;
  revenue_pending_count: number;
  expense_reconciled_count: number;
  expense_pending_count: number;
}>;

export type FinanceIntegritySummary = Readonly<{
  totalMonths: number;
  readyMonths: number;
  needsDataMonths: number;
  needsReviewMonths: number;
  blockedMonths: number;
  reconciledValues: number;
  pendingValues: number;
}>;

export function financeIntegrityStatusLabel(
  status: FinanceIntegrityStatus,
): string;

export function summarizeFinanceIntegrity(
  items: readonly FinanceIntegritySummaryItem[],
): FinanceIntegritySummary;
