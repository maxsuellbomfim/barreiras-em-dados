export function financeIntegrityStatusLabel(status) {
  if (status === "ready") return "Pronto para leitura";
  if (status === "needs_data") return "Faltam dados";
  if (status === "needs_review") return "Requer reconciliação";
  return "Publicação bloqueada";
}

export function summarizeFinanceIntegrity(items) {
  return items.reduce(
    (summary, item) => ({
      totalMonths: summary.totalMonths + 1,
      readyMonths: summary.readyMonths + (item.diagnostic_status === "ready" ? 1 : 0),
      needsDataMonths:
        summary.needsDataMonths + (item.diagnostic_status === "needs_data" ? 1 : 0),
      needsReviewMonths:
        summary.needsReviewMonths
        + (item.diagnostic_status === "needs_review" ? 1 : 0),
      blockedMonths:
        summary.blockedMonths + (item.diagnostic_status === "blocked" ? 1 : 0),
      reconciledValues:
        summary.reconciledValues
        + item.revenue_reconciled_count
        + item.expense_reconciled_count,
      pendingValues:
        summary.pendingValues
        + item.revenue_pending_count
        + item.expense_pending_count,
    }),
    {
      totalMonths: 0,
      readyMonths: 0,
      needsDataMonths: 0,
      needsReviewMonths: 0,
      blockedMonths: 0,
      reconciledValues: 0,
      pendingValues: 0,
    },
  );
}
