import assert from "node:assert/strict";
import test from "node:test";

import {
  monthlyFinanceHref,
  monthlyFinanceStatusCopy,
  parseMonthlyFinanceDetail,
  periodStartFromSlug,
} from "../../apps/web/lib/monthly-finance-detail.mjs";

const validRow = {
  closure_id: "body-1:2026-06-01",
  fiscal_year: 2026,
  period_start: "2026-06-01",
  period_end: "2026-06-30",
  public_body_name: "Município de Barreiras",
  revenue_report_amount: "2700.00",
  revenue_report_count: 2,
  revenue_line_count: 42,
  expense_paid_amount: "1200.00",
  expense_committed_amount: "1600.00",
  expense_liquidated_amount: "1400.00",
  expense_report_count: 2,
  operational_difference_amount: null,
  closure_status: "needs_review",
  coverage_note: "Existem versões que precisam de reconciliação.",
  calculation_methodology: "monthly-finance-closure/1.1.0",
  revenue_documents: [
    {
      document_url: "https://dados.barreiras.ba.gov.br/receita-junho.pdf",
      artifact_sha256: "a".repeat(64),
      source_url: "https://dados.barreiras.ba.gov.br/api/receitas",
      source_artifact_sha256: "b".repeat(64),
      line_count: 42,
      report_amount: "2700.00",
    },
    {
      document_url: "https://dados.barreiras.ba.gov.br/receita-junho-v2.pdf",
      artifact_sha256: "e".repeat(64),
      source_url: "https://dados.barreiras.ba.gov.br/api/receitas",
      source_artifact_sha256: "f".repeat(64),
      line_count: 42,
      report_amount: "2700.00",
    },
  ],
  expense_documents: [
    {
      document_url: "https://dados.barreiras.ba.gov.br/despesa-junho.pdf",
      artifact_sha256: "c".repeat(64),
      source_url: "https://dados.barreiras.ba.gov.br/api/despesas",
      source_artifact_sha256: "d".repeat(64),
      committed_amount: "1600.00",
      liquidated_amount: "1400.00",
      paid_amount: "1200.00",
    },
    {
      document_url: "https://dados.barreiras.ba.gov.br/despesa-junho-v2.pdf",
      artifact_sha256: "1".repeat(64),
      source_url: "https://dados.barreiras.ba.gov.br/api/despesas",
      source_artifact_sha256: "2".repeat(64),
      committed_amount: "1600.00",
      liquidated_amount: "1400.00",
      paid_amount: "1200.00",
    },
  ],
  evidence_methodology: "public-monthly-finance-detail/1.0.0",
};

test("valida o fechamento e preserva os documentos oficiais do mês", () => {
  const detail = parseMonthlyFinanceDetail(validRow);

  assert.equal(detail?.periodStart, "2026-06-01");
  assert.equal(detail?.operationalDifferenceAmount, null);
  assert.equal(detail?.revenueDocuments[0]?.reportAmount, "2700.00");
  assert.equal(
    detail?.expenseDocuments[0]?.documentUrl,
    "https://dados.barreiras.ba.gov.br/despesa-junho.pdf",
  );
  assert.equal(detail?.revenueDocuments.length, 2);
  assert.equal(detail?.expenseDocuments.length, 2);
});

test("rejeita evidência sem HTTPS, hash ou metodologia conhecida", () => {
  assert.equal(
    parseMonthlyFinanceDetail({
      ...validRow,
      revenue_documents: [
        { ...validRow.revenue_documents[0], document_url: "http://inseguro.test/doc.pdf" },
      ],
    }),
    null,
  );
  assert.equal(
    parseMonthlyFinanceDetail({
      ...validRow,
      expense_documents: [
        { ...validRow.expense_documents[0], artifact_sha256: "curto" },
      ],
    }),
    null,
  );
  assert.equal(
    parseMonthlyFinanceDetail({ ...validRow, evidence_methodology: "desconhecida" }),
    null,
  );
  assert.equal(
    parseMonthlyFinanceDetail({ ...validRow, expense_documents: [] }),
    null,
  );
});

test("converte somente competências mensais válidas em rota pública", () => {
  assert.equal(periodStartFromSlug("2026-06"), "2026-06-01");
  assert.equal(periodStartFromSlug("2026-13"), null);
  assert.equal(periodStartFromSlug("2026-6"), null);
  assert.equal(monthlyFinanceHref("2026-06-01"), "/financas/2026-06");
});

test("não apresenta diferença como resultado quando o mês exige reconciliação", () => {
  const detail = parseMonthlyFinanceDetail(validRow);
  assert.deepEqual(monthlyFinanceStatusCopy(detail), {
    label: "Requer reconciliação",
    heading: "Este mês ainda tem versões para conferir",
    explanation:
      "Existem versões que precisam de reconciliação. Os documentos continuam visíveis, mas a diferença entre receita e pagamentos permanece indisponível para evitar dupla contagem.",
    canShowDifference: false,
  });
});

test("explica a diferença operacional sem chamá-la de superávit", () => {
  const detail = parseMonthlyFinanceDetail({
    ...validRow,
    revenue_report_count: 1,
    expense_report_count: 1,
    revenue_documents: [validRow.revenue_documents[0]],
    expense_documents: [validRow.expense_documents[0]],
    operational_difference_amount: "1500.00",
    closure_status: "operational",
    coverage_note: "As duas fontes são comparáveis.",
  });
  assert.deepEqual(monthlyFinanceStatusCopy(detail), {
    label: "Mês comparável",
    heading: "A receita declarada ficou acima dos pagamentos",
    explanation:
      "A diferença operacional é receita declarada menos pagamentos do mesmo mês. Ela não representa saldo bancário, superávit fiscal nem dinheiro livre em caixa.",
    canShowDifference: true,
  });
});
