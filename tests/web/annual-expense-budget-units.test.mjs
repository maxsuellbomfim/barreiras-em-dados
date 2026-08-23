import assert from "node:assert/strict";
import test from "node:test";

import { buildAnnualExpenseBudgetUnits } from "../../apps/web/lib/annual-expense-budget-units.mjs";

const JAN_REPORT = "00000000-0000-4000-8000-000000000201";
const FEB_REPORT = "00000000-0000-4000-8000-000000000202";

function closure(periodStart, expensePaidAmount, closureStatus = "operational") {
  return { fiscalYear: 2025, periodStart, closureStatus, expensePaidAmount };
}

function report(expenseReportId, periodStart, totalPaidPeriodAmount) {
  return {
    expenseReportId,
    fiscalYear: 2025,
    periodStart,
    totalPaidPeriodAmount,
    documentSourceUrl: `https://barreiras.example/${expenseReportId}.pdf`,
    documentArtifactSha256: expenseReportId === JAN_REPORT ? "c".repeat(64) : "d".repeat(64),
  };
}

function unit(expenseReportId, code, name, paid, reportTotal) {
  return {
    expenseReportId,
    budgetUnitCode: code,
    budgetUnitName: name,
    budgetUnitNameCount: 1,
    lineCount: 1,
    reportLineCount: 2,
    allocatedLineCount: 2,
    committedPeriodAmount: paid,
    liquidatedPeriodAmount: paid,
    paidPeriodAmount: paid,
    reportTotalPaidAmount: reportTotal,
    allocatedTotalPaidAmount: reportTotal,
    paidSharePercent: "0.00",
    methodologyVersion: "public-expense-budget-unit-summary/1.0.0",
  };
}

test("soma unidades em centavos e mantém os 12 meses e as fontes", () => {
  const result = buildAnnualExpenseBudgetUnits({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, { state: "available", budgetUnits: [
        unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "80.08", "100.10"),
        unit(JAN_REPORT, "030501", "SECRETARIA MUNICIPAL DE ADMINISTRACAO", "20.02", "100.10"),
      ] }],
      [FEB_REPORT, { state: "available", budgetUnits: [
        unit(FEB_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "100.10", "200.20"),
        unit(FEB_REPORT, "030501", "SECRETARIA MUNICIPAL DE ADMINISTRACAO", "100.10", "200.20"),
      ] }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.unitCoveredMonthCount, 2);
  assert.equal(result.annualPaidAmount, "300.30");
  assert.deepEqual(result.budgetUnits.map((item) => ({
    code: item.budgetUnitCode,
    paid: item.paidAmount,
    share: item.paidSharePercent,
  })), [
    { code: "031101", paid: "180.18", share: "60.00" },
    { code: "030501", paid: "120.12", share: "40.00" },
  ]);
  assert.equal(result.budgetUnits[0].months.length, 12);
  assert.equal(result.budgetUnits[0].months[0].documentArtifactSha256, "c".repeat(64));
  assert.equal(result.budgetUnits[0].months[2].paidAmount, null);
});

test("não converte mês sem atribuição integral em zero", () => {
  const result = buildAnnualExpenseBudgetUnits({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, { state: "available", budgetUnits: [
        unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "100.10", "100.10"),
      ] }],
      [FEB_REPORT, { state: "conflict", reason: "partial", reportLineCount: 2, allocatedLineCount: 1 }],
    ]),
  });

  assert.equal(result.state, "available");
  assert.equal(result.unitCoveredMonthCount, 1);
  assert.equal(result.budgetUnits[0].months[1].paidAmount, null);
});

test("registra zero só quando o relatório integral prova que a unidade não apareceu", () => {
  const result = buildAnnualExpenseBudgetUnits({
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")],
    reports: [
      report(JAN_REPORT, "2025-01-01", "100.10"),
      report(FEB_REPORT, "2025-02-01", "200.20"),
    ],
    summariesByReport: new Map([
      [JAN_REPORT, { state: "available", budgetUnits: [
        unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "80.08", "100.10"),
        unit(JAN_REPORT, "030501", "SECRETARIA MUNICIPAL DE ADMINISTRACAO", "20.02", "100.10"),
      ] }],
      [FEB_REPORT, { state: "available", budgetUnits: [
        { ...unit(FEB_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "200.20", "200.20"), reportLineCount: 1, allocatedLineCount: 1 },
      ] }],
    ]),
  });

  assert.equal(result.state, "available");
  const administration = result.budgetUnits.find((item) => item.budgetUnitCode === "030501");
  assert.equal(administration.months[1].paidAmount, "0.00");
  assert.equal(administration.months[1].documentSourceUrl, `https://barreiras.example/${FEB_REPORT}.pdf`);
});

test("bloqueia divergência financeira e mudança de nome para o mesmo código no ano", () => {
  const base = {
    fiscalYear: 2025,
    closures: [closure("2025-01-01", "100.10")],
    reports: [report(JAN_REPORT, "2025-01-01", "100.09")],
    summariesByReport: new Map([[JAN_REPORT, { state: "available", budgetUnits: [
      unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "100.09", "100.09"),
    ] }]]),
  };
  assert.deepEqual(buildAnnualExpenseBudgetUnits(base), {
    state: "conflict", periodStart: "2025-01-01", reason: "expense_total_mismatch",
  });

  base.reports = [report(JAN_REPORT, "2025-01-01", "100.10")];
  base.summariesByReport = new Map([[JAN_REPORT, { state: "available", budgetUnits: [
    unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "100.09", "100.10"),
  ] }]]);
  assert.deepEqual(buildAnnualExpenseBudgetUnits(base), {
    state: "conflict", periodStart: "2025-01-01", reason: "unit_total_mismatch",
  });

  base.closures = [closure("2025-01-01", "100.10"), closure("2025-02-01", "200.20")];
  base.reports = [report(JAN_REPORT, "2025-01-01", "100.10"), report(FEB_REPORT, "2025-02-01", "200.20")];
  base.summariesByReport = new Map([
    [JAN_REPORT, { state: "available", budgetUnits: [unit(JAN_REPORT, "031101", "SECRETARIA MUNICIPAL DE SAUDE", "100.10", "100.10")] }],
    [FEB_REPORT, { state: "available", budgetUnits: [{ ...unit(FEB_REPORT, "031101", "FUNDO MUNICIPAL DE SAUDE", "200.20", "200.20"), reportLineCount: 1, allocatedLineCount: 1 }] }],
  ]);
  assert.deepEqual(buildAnnualExpenseBudgetUnits(base), {
    state: "conflict", periodStart: "2025-02-01", reason: "unit_name_conflict",
  });
});
