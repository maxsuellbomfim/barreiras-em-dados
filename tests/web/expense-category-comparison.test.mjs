import assert from "node:assert/strict";
import test from "node:test";

import {
  compareExpenseCategoryMonths,
  previousMonthStart,
} from "../../apps/web/lib/expense-category-comparison.mjs";

function category(code, paid, total, description = `Categoria ${code}`) {
  return {
    expenseReportId: "00000000-0000-4000-8000-000000000001",
    expenseCode: code,
    sourceDescription: description,
    sourceDescriptionCount: 1,
    lineCount: 1,
    committedPeriodAmount: paid,
    liquidatedPeriodAmount: paid,
    paidPeriodAmount: paid,
    reportTotalPaidAmount: total,
    aggregatedTotalPaidAmount: total,
    paidSharePercent: "50.00",
    methodologyVersion: "public-expense-category-summary/1.0.0",
  };
}

test("encontra o mês imediatamente anterior inclusive na virada do ano", () => {
  assert.equal(previousMonthStart("2026-07-01"), "2026-06-01");
  assert.equal(previousMonthStart("2026-01-01"), "2025-12-01");
  assert.equal(previousMonthStart("2026-07-15"), null);
});

test("compara centavos exatamente e conserva categoria ausente como não localizada", () => {
  const result = compareExpenseCategoryMonths(
    {
      state: "available",
      categories: [
        category("A", "100.10", "125.15"),
        category("B", "25.05", "125.15"),
      ],
    },
    {
      state: "available",
      categories: [category("A", "80.09", "80.09")],
    },
  );

  assert.deepEqual(result, {
    state: "available",
    currentTotalPaidAmount: "125.15",
    previousTotalPaidAmount: "80.09",
    totalDifferenceAmount: "45.06",
    categories: [
      {
        expenseCode: "A",
        sourceDescription: "Categoria A",
        currentPaidAmount: "100.10",
        previousPaidAmount: "80.09",
        differenceAmount: "20.01",
      },
      {
        expenseCode: "B",
        sourceDescription: "Categoria B",
        currentPaidAmount: "25.05",
        previousPaidAmount: null,
        differenceAmount: null,
      },
    ],
  });
});

test("não compara relatório não reconciliado ou sem mês anterior", () => {
  const available = {
    state: "available",
    categories: [category("A", "1.00", "1.00")],
  };
  assert.deepEqual(compareExpenseCategoryMonths(available, { state: "empty" }), {
    state: "unavailable",
  });
  assert.deepEqual(
    compareExpenseCategoryMonths({ state: "conflict" }, available),
    { state: "unavailable" },
  );
});
