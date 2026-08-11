import assert from "node:assert/strict";
import test from "node:test";

import {
  financeIntegrityStatusLabel,
  summarizeFinanceIntegrity,
} from "../../apps/admin/app/finance-integrity.mjs";

const rows = [
  {
    diagnostic_status: "ready",
    revenue_reconciled_count: 0,
    revenue_pending_count: 0,
    expense_reconciled_count: 0,
    expense_pending_count: 0,
  },
  {
    diagnostic_status: "blocked",
    revenue_reconciled_count: 5,
    revenue_pending_count: 1,
    expense_reconciled_count: 2,
    expense_pending_count: 3,
  },
  {
    diagnostic_status: "needs_review",
    revenue_reconciled_count: 7,
    revenue_pending_count: 0,
    expense_reconciled_count: 1,
    expense_pending_count: 0,
  },
  {
    diagnostic_status: "needs_data",
    revenue_reconciled_count: 0,
    revenue_pending_count: 0,
    expense_reconciled_count: 0,
    expense_pending_count: 0,
  },
];

test("resume meses e valores reconciliados sem esconder pendencias", () => {
  assert.deepEqual(summarizeFinanceIntegrity(rows), {
    totalMonths: 4,
    readyMonths: 1,
    needsDataMonths: 1,
    needsReviewMonths: 1,
    blockedMonths: 1,
    reconciledValues: 15,
    pendingValues: 4,
  });
});

test("traduz estados tecnicos em rotulos compreensiveis", () => {
  assert.equal(financeIntegrityStatusLabel("ready"), "Pronto para leitura");
  assert.equal(financeIntegrityStatusLabel("needs_data"), "Faltam dados");
  assert.equal(financeIntegrityStatusLabel("needs_review"), "Requer reconciliação");
  assert.equal(financeIntegrityStatusLabel("blocked"), "Publicação bloqueada");
});
