import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFinanceCoverageMatrix,
  financeCoverageStatusLabel,
  parseFinanceCoverageApiPayload,
} from "../../apps/web/lib/finance-coverage-matrix.mjs";

function coverageRow({
  body = "Prefeitura Municipal de Barreiras",
  month,
  status,
  revenue = 0,
  expense = 0,
}) {
  const [year, monthNumber] = month.split("-").map(Number);
  const periodEnd = new Date(Date.UTC(year, monthNumber, 0))
    .toISOString()
    .slice(0, 10);
  return {
    coverageId: `${body}:${month}`,
    fiscalYear: year,
    periodStart: `${month}-01`,
    periodEnd,
    publicBodyName: body,
    revenueReportCount: revenue,
    expenseReportCount: expense,
    coverageStatus: status,
    coverageNote: `Situação oficial de ${month}.`,
    calculationMethodology: "finance-coverage/1.1.0",
  };
}

test("matriz não transforma competência ausente da resposta em mês sem relatório", () => {
  const result = buildFinanceCoverageMatrix([
    coverageRow({ month: "2021-01", status: "complete", revenue: 1, expense: 1 }),
    coverageRow({ month: "2021-02", status: "revenue_only", revenue: 1 }),
    coverageRow({ month: "2021-04", status: "missing" }),
  ]);

  assert.ok(result);
  assert.equal(result.bodies.length, 1);
  assert.equal(result.bodies[0].years.length, 1);
  assert.deepEqual(
    result.bodies[0].years[0].months.slice(0, 4).map((month) => ({
      month: month.month,
      status: month.status,
    })),
    [
      { month: 1, status: "complete" },
      { month: 2, status: "revenue_only" },
      { month: 3, status: "unclassified" },
      { month: 4, status: "missing" },
    ],
  );
  assert.equal(result.bodies[0].years[0].months[4].status, "not_due");
});

test("competência corrente sem relatório fica em andamento sem ocultar lacuna anterior", () => {
  const result = buildFinanceCoverageMatrix([
    coverageRow({ month: "2026-08", status: "missing" }),
    coverageRow({ month: "2026-09", status: "missing" }),
  ], 2021, "2026-09");

  assert.ok(result);
  const currentYear = result.bodies[0].years[0];
  assert.equal(currentYear.year, 2026);
  assert.equal(currentYear.months[7].status, "missing");
  assert.equal(currentYear.months[8].status, "not_due");
  assert.equal(currentYear.months[8].row?.periodStart, "2026-09-01");
});

test("matriz mantém órgãos separados e fecha quando uma competência está duplicada", () => {
  const prefeitura = coverageRow({ month: "2021-01", status: "complete", revenue: 1, expense: 1 });
  const autarquia = coverageRow({
    body: "Autarquia Municipal",
    month: "2021-01",
    status: "expense_only",
    expense: 1,
  });

  const separated = buildFinanceCoverageMatrix([prefeitura, autarquia]);
  assert.ok(separated);
  assert.deepEqual(
    separated.bodies.map((body) => body.publicBodyName),
    ["Autarquia Municipal", "Prefeitura Municipal de Barreiras"],
  );
  assert.equal(buildFinanceCoverageMatrix([prefeitura, prefeitura]), null);
});

test("rótulos explicam todos os estados sem depender apenas de cor", () => {
  assert.deepEqual(
    ["complete", "revenue_only", "expense_only", "needs_review", "missing", "unclassified", "not_due"]
      .map((status) => financeCoverageStatusLabel(status)),
    [
      "Receita e despesa",
      "Só receita",
      "Só despesa",
      "Revisão necessária",
      "Sem relatório validado",
      "Não classificado",
      "Competência em andamento ou futura",
    ],
  );
});

test("payload público só é aceito quando todas as competências respeitam o contrato", () => {
  const validRow = coverageRow({
    month: "2021-01",
    status: "complete",
    revenue: 1,
    expense: 1,
  });

  assert.deepEqual(
    parseFinanceCoverageApiPayload({ state: "available", rows: [validRow] }),
    { state: "available", rows: [validRow] },
  );
  assert.deepEqual(parseFinanceCoverageApiPayload({ state: "unavailable" }), {
    state: "unavailable",
  });
  assert.equal(
    parseFinanceCoverageApiPayload({
      state: "available",
      rows: [{ ...validRow, expenseReportCount: -1 }],
    }),
    null,
  );
  assert.equal(
    parseFinanceCoverageApiPayload({
      state: "available",
      rows: [{ ...validRow, coverageNote: "" }],
    }),
    null,
  );
});
