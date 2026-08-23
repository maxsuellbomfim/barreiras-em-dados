import assert from "node:assert/strict";
import test from "node:test";

import { buildAnnualExpenseCategories } from "../../apps/web/lib/annual-expense-categories.mjs";

const JAN_REPORT = "00000000-0000-4000-8000-000000000101";
const FEB_REPORT = "00000000-0000-4000-8000-000000000102";

function closure(periodStart, expensePaidAmount, closureStatus = "operational") {
  return {
    fiscalYear: 2025,
    periodStart,
    closureStatus,
    expensePaidAmount,
  };
}

function report(expenseReportId, periodStart, totalPaidPeriodAmount) {
  return {
    expenseReportId,
    fiscalYear: 2025,
    periodStart,
    totalPaidPeriodAmount,
    documentSourceUrl: `https://barreiras.example/${expenseReportId}.pdf`,
    documentArtifactSha256: expenseReportId === JAN_REPORT ? "a".repeat(64) : "b".repeat(64),
  };
}

function category(
  expenseReportId,
  expenseCode,
  sourceDescription,
  paidPeriodAmount,
  reportTotalPaidAmount,
) {
  return {
    expenseReportId,
    expenseCode,
    sourceDescription,
    sourceDescriptionCount: 1,
    lineCount: 1,
    committedPeriodAmount: paidPeriodAmount,
    liquidatedPeriodAmount: paidPeriodAmount,
    paidPeriodAmount,
    reportTotalPaidAmount,
    aggregatedTotalPaidAmount: reportTotalPaidAmount,
    paidSharePercent: "0.00",
    methodologyVersion: "public-expense-category-summary/1.0.0",
  };
}

test("soma categorias do ano em centavos e mantém a evolução mensal rastreável", () => {
  const result = buildAnnualExpenseCategories({
    fiscalYear: 2025,
    closures: [
      closure("2025-01-01", "100.10"),
      closure("2025-02-01", "200.20"),
      closure("2025-03-01", null, "needs_data"),
    ],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, {
        state: "available",
        categories: [
          category(JAN_REPORT, "A", "Categoria A", "80.08", "100.10"),
          category(JAN_REPORT, "B", "Categoria B", "20.02", "100.10"),
        ],
      }],
      [FEB_REPORT, {
        state: "available",
        categories: [
          category(FEB_REPORT, "A", "Categoria A", "100.10", "200.20"),
          category(FEB_REPORT, "B", "Categoria B", "100.10", "200.20"),
        ],
      }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.comparableMonthCount, 2);
  assert.equal(result.categoryCoveredMonthCount, 2);
  assert.equal(result.annualPaidAmount, "300.30");
  assert.deepEqual(
    result.categories.map((item) => ({
      code: item.expenseCode,
      paid: item.paidAmount,
      share: item.paidSharePercent,
      months: item.monthCount,
    })),
    [
      { code: "A", paid: "180.18", share: "60.00", months: 2 },
      { code: "B", paid: "120.12", share: "40.00", months: 2 },
    ],
  );
  assert.deepEqual(result.categories[0].months.slice(0, 3), [
    {
      periodStart: "2025-01-01",
      paidAmount: "80.08",
      barBasisPoints: 8000,
      documentSourceUrl: `https://barreiras.example/${JAN_REPORT}.pdf`,
      documentArtifactSha256: "a".repeat(64),
    },
    {
      periodStart: "2025-02-01",
      paidAmount: "100.10",
      barBasisPoints: 10000,
      documentSourceUrl: `https://barreiras.example/${FEB_REPORT}.pdf`,
      documentArtifactSha256: "b".repeat(64),
    },
    {
      periodStart: "2025-03-01",
      paidAmount: null,
      barBasisPoints: null,
      documentSourceUrl: null,
      documentArtifactSha256: null,
    },
  ]);
});

test("exclui mês sem resumo reconciliado em vez de convertê-lo em zero", () => {
  const result = buildAnnualExpenseCategories({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, {
        state: "available",
        categories: [category(JAN_REPORT, "A", "Categoria A", "100.10", "100.10")],
      }],
      [FEB_REPORT, { state: "unavailable" }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.comparableMonthCount, 2);
  assert.equal(result.categoryCoveredMonthCount, 1);
  assert.equal(result.annualPaidAmount, "100.10");
  assert.equal(result.categories[0].months[1].paidAmount, null);
});

test("registra zero somente quando o relatório reconciliado comprova ausência da categoria", () => {
  const result = buildAnnualExpenseCategories({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, {
        state: "available",
        categories: [
          category(JAN_REPORT, "A", "Categoria A", "80.08", "100.10"),
          category(JAN_REPORT, "B", "Categoria B", "20.02", "100.10"),
        ],
      }],
      [FEB_REPORT, {
        state: "available",
        categories: [category(FEB_REPORT, "A", "Categoria A", "200.20", "200.20")],
      }],
    ]),
  });

  assert.equal(result.state, "available");
  const categoryB = result.categories.find((item) => item.expenseCode === "B");
  assert.equal(categoryB.monthCount, 1);
  assert.equal(categoryB.months[1].paidAmount, "0.00");
  assert.equal(categoryB.months[1].barBasisPoints, 0);
  assert.equal(categoryB.months[1].documentSourceUrl, `https://barreiras.example/${FEB_REPORT}.pdf`);
});

test("bloqueia divergência entre fechamento, relatório e soma das categorias", () => {
  const common = {
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10")],
    reports: [report(JAN_REPORT, "2025-01-01", "100.09")],
    summariesByReport: new Map([
      [JAN_REPORT, {
        state: "available",
        categories: [category(JAN_REPORT, "A", "Categoria A", "100.09", "100.09")],
      }],
    ]),
  };

  assert.deepEqual(buildAnnualExpenseCategories(common), {
    state: "conflict",
    periodStart: "2025-01-01",
    reason: "expense_total_mismatch",
  });

  common.reports = [report(JAN_REPORT, "2025-01-01", "100.10")];
  common.summariesByReport = new Map([
    [JAN_REPORT, {
      state: "available",
      categories: [category(JAN_REPORT, "A", "Categoria A", "100.09", "100.10")],
    }],
  ]);
  assert.deepEqual(buildAnnualExpenseCategories(common), {
    state: "conflict",
    periodStart: "2025-01-01",
    reason: "category_total_mismatch",
  });
});

test("rejeita relatório mensal duplicado e valores decimais inválidos", () => {
  const base = {
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-01-01", "100.10"),
    ],
    summariesByReport: new Map(),
  };
  assert.deepEqual(buildAnnualExpenseCategories(base), { state: "unavailable" });

  base.reports = [report(JAN_REPORT, "2025-01-01", "1e2")];
  assert.deepEqual(buildAnnualExpenseCategories(base), { state: "unavailable" });
});

test("ignora versões duplicadas de mês que o fechamento já marcou como não comparável", () => {
  const result = buildAnnualExpenseCategories({
    fiscalYear: 2025,
    closures: [
      closure("2025-01-01", "100.10"),
      closure("2025-02-01", null, "needs_review"),
    ],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
      report("00000000-0000-4000-8000-000000000103", "2025-02-01", "300.30"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, {
        state: "available",
        categories: [category(JAN_REPORT, "A", "Categoria A", "100.10", "100.10")],
      }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.categoryCoveredMonthCount, 1);
});

test("informa variação de descrição sem inventar quantas grafias únicas houve no ano", () => {
  const varied = {
    ...category(JAN_REPORT, "A", "SERVICOS", "100.10", "100.10"),
    sourceDescriptionCount: 2,
    lineCount: 2,
  };
  const result = buildAnnualExpenseCategories({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10")],
    reports: [report(JAN_REPORT, "2025-01-01", "100.10")],
    summariesByReport: new Map([
      [JAN_REPORT, { state: "available", categories: [varied] }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.categories[0].descriptionVariationObserved, true);
  assert.equal("sourceDescriptionCount" in result.categories[0], false);
});
