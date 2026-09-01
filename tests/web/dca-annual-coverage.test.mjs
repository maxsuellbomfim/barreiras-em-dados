import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildDcaAnnualCoverage,
  dcaAnnualCoverageStatusLabel,
} from "../../apps/web/lib/dca-annual-coverage.mjs";

const component = await readFile(
  new URL("../../apps/web/app/financas/finance-dca-annual-coverage.tsx", import.meta.url),
  "utf8",
);
const annual = await readFile(
  new URL("../../apps/web/app/financas/finance-siconfi-annual-totals.tsx", import.meta.url),
  "utf8",
);

function year(fiscalYear) {
  return {
    fiscalYear,
    metrics: Array.from({ length: 7 }, (_, index) => ({
      sourceUrl: `https://apidatalake.tesouro.gov.br/dca/${fiscalYear}/${index}`,
    })),
  };
}

test("matriz anual distingue DCA publicada, não localizada e exercício em andamento", () => {
  const coverage = buildDcaAnnualCoverage(
    [year(2021), year(2023), year(2025)],
    { yearFrom: 2021, currentYear: 2026 },
  );

  assert.deepEqual(
    coverage.map(({ fiscalYear, status }) => ({ fiscalYear, status })),
    [
      { fiscalYear: 2026, status: "in_progress" },
      { fiscalYear: 2025, status: "published" },
      { fiscalYear: 2024, status: "not_found" },
      { fiscalYear: 2023, status: "published" },
      { fiscalYear: 2022, status: "not_found" },
      { fiscalYear: 2021, status: "published" },
    ],
  );
});

test("matriz falha fechada diante de ano duplicado, futuro ou incompleto", () => {
  assert.equal(
    buildDcaAnnualCoverage([year(2024), year(2024)], { yearFrom: 2021, currentYear: 2026 }),
    null,
  );
  assert.equal(
    buildDcaAnnualCoverage([year(2027)], { yearFrom: 2021, currentYear: 2026 }),
    null,
  );
  assert.equal(
    buildDcaAnnualCoverage([{ ...year(2024), metrics: [] }], {
      yearFrom: 2021,
      currentYear: 2026,
    }),
    null,
  );
});

test("rótulos não convertem ausência documental em valor zero", () => {
  assert.equal(dcaAnnualCoverageStatusLabel("published"), "DCA publicada");
  assert.equal(dcaAnnualCoverageStatusLabel("not_found"), "Não localizada na consulta");
  assert.equal(dcaAnnualCoverageStatusLabel("in_progress"), "Exercício em andamento");
  assert.doesNotMatch(component, /gasto zero|receita zero/i);
  assert.match(component, /não significa valor zero/i);
});

test("retrato anual incorpora a matriz antes dos valores", () => {
  assert.match(annual, /FinanceDcaAnnualCoverage/);
  assert.ok(
    annual.indexOf("<FinanceDcaAnnualCoverage") <
      annual.indexOf('<article className="finance-siconfi-latest">'),
  );
});
