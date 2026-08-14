import assert from "node:assert/strict";
import test from "node:test";

const summaryModule = await import(
  "../../apps/web/lib/parliamentary-transfer-citizen-summary.mjs"
).catch(() => ({ buildCurrentTransferCitizenSummary: () => null }));

const { buildCurrentTransferCitizenSummary } = summaryModule;

test("leitura cidadã usa somente o ano mais recente e soma centavos exatamente", () => {
  const summary = buildCurrentTransferCitizenSummary([
    {
      fiscalYear: 2024,
      destinationAmount: "999999999.99",
      committedAmount: "999999999.99",
      paidAmount: "999999999.99",
    },
    {
      fiscalYear: 2025,
      destinationAmount: "5000000.10",
      committedAmount: "5000000.10",
      paidAmount: "5000000.10",
    },
    {
      fiscalYear: 2025,
      destinationAmount: "2000000.20",
      committedAmount: "2000000.20",
      paidAmount: "2000000.20",
    },
    {
      fiscalYear: 2025,
      destinationAmount: "250000.03",
      committedAmount: null,
      paidAmount: null,
    },
  ]);

  assert.deepEqual(summary, {
    fiscalYear: 2025,
    transferCount: 3,
    destinationAmount: "7250000.33",
    committedAmount: "7000000.30",
    paidAmount: "7000000.30",
    commitmentFoundCount: 2,
    paymentFoundCount: 2,
    paymentNotFoundCount: 1,
    destinationWithoutPaymentAmount: "250000.03",
  });
});

test("ausência de pagamento permanece explícita quando nenhum pagamento foi localizado", () => {
  const summary = buildCurrentTransferCitizenSummary([
    {
      fiscalYear: 2026,
      destinationAmount: "125.00",
      committedAmount: null,
      paidAmount: null,
    },
  ]);

  assert.deepEqual(summary, {
    fiscalYear: 2026,
    transferCount: 1,
    destinationAmount: "125.00",
    committedAmount: null,
    paidAmount: null,
    commitmentFoundCount: 0,
    paymentFoundCount: 0,
    paymentNotFoundCount: 1,
    destinationWithoutPaymentAmount: "125.00",
  });
});

test("sem transferências atuais não fabrica um resumo financeiro", () => {
  assert.equal(buildCurrentTransferCitizenSummary([]), null);
});
