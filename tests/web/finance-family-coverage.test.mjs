import assert from "node:assert/strict";
import test from "node:test";

import { buildFinanceFamilyCoverage } from "../../apps/web/lib/finance-family-coverage.mjs";

test("resume cada família na sua própria periodicidade sem criar taxa global", () => {
  const families = buildFinanceFamilyCoverage({
    financeRows: [
      { periodStart: "2026-07-01", coverageStatus: "complete" },
      { periodStart: "2026-06-01", coverageStatus: "expense_only" },
    ],
    obligationRows: [
      { periodStart: "2026-07-01", coverageStatus: "published" },
      { periodStart: "2026-06-01", coverageStatus: "section_absent" },
    ],
    payrollRows: [
      { referenceMonth: "2026-07-01", coverageStatus: "published" },
      { referenceMonth: "2026-06-01", coverageStatus: "processing_pending" },
    ],
    fiscalDocuments: [
      { sourceResource: "rreo", referenceDate: "2026-06-30", fiscalYear: 2026 },
      { sourceResource: "rgf", referenceDate: "2026-04-30", fiscalYear: 2026 },
    ],
    siconfiYears: [{ fiscalYear: 2025 }, { fiscalYear: 2024 }],
  });

  assert.deepEqual(
    families.map(({ key, cadence, observedPeriods, classifiedPeriods, gapPeriods, state }) => ({
      key,
      cadence,
      observedPeriods,
      classifiedPeriods,
      gapPeriods,
      state,
    })),
    [
      {
        key: "monthly-finance",
        cadence: "Mensal",
        observedPeriods: 1,
        classifiedPeriods: 2,
        gapPeriods: 1,
        state: "partial",
      },
      {
        key: "obligations",
        cadence: "Mensal",
        observedPeriods: 1,
        classifiedPeriods: 2,
        gapPeriods: 1,
        state: "partial",
      },
      {
        key: "payroll",
        cadence: "Mensal",
        observedPeriods: 1,
        classifiedPeriods: 2,
        gapPeriods: 1,
        state: "partial",
      },
      {
        key: "fiscal-statements",
        cadence: "Bimestral e quadrimestral",
        observedPeriods: 2,
        classifiedPeriods: null,
        gapPeriods: null,
        state: "observed",
      },
      {
        key: "annual-accounts",
        cadence: "Anual",
        observedPeriods: 2,
        classifiedPeriods: null,
        gapPeriods: null,
        state: "observed",
      },
    ],
  );
  assert.equal(families.some((family) => "coverageRate" in family), false);
});

test("distingue fonte indisponível de período classificado sem publicação", () => {
  const families = buildFinanceFamilyCoverage({
    financeRows: [{ periodStart: "2025-01-01", coverageStatus: "missing" }],
    obligationRows: [],
    payrollRows: [],
    fiscalDocuments: [],
    siconfiYears: [],
  });

  assert.equal(families[0].state, "partial");
  assert.equal(families[0].classifiedPeriods, 1);
  assert.equal(families[0].observedPeriods, 0);
  assert.equal(families[0].latestObservedPeriod, null);
  assert.equal(families[1].state, "unavailable");
  assert.equal(families[3].state, "unavailable");
});

test("remove duplicidades de documentos e anos observados", () => {
  const families = buildFinanceFamilyCoverage({
    financeRows: [],
    obligationRows: [],
    payrollRows: [],
    fiscalDocuments: [
      { sourceResource: "rreo", referenceDate: "2025-12-31", fiscalYear: 2025 },
      { sourceResource: "rreo", referenceDate: "2025-12-31", fiscalYear: 2025 },
      { sourceResource: "rgf", referenceDate: "2026-04-30", fiscalYear: 2026 },
    ],
    siconfiYears: [{ fiscalYear: 2025 }, { fiscalYear: 2025 }],
  });

  assert.equal(families[3].observedPeriods, 2);
  assert.equal(families[4].observedPeriods, 1);
  assert.equal(families[3].latestObservedPeriod, "2026-04-30");
  assert.equal(families[4].latestObservedPeriod, "2025");
});
