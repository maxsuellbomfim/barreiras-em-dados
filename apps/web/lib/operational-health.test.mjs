import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildOperationalHealth } from "./operational-health.mjs";

test("saúde pública fica ok somente quando os três domínios respondem com dados", () => {
  const result = buildOperationalHealth({
    checkedAt: "2026-08-31T12:00:00.000Z",
    diary: { state: "available", records: 4706 },
    finance: { state: "available", records: 48 },
    representatives: { state: "available", records: 19 },
  });

  assert.equal(result.status, "ok");
  assert.equal(result.httpStatus, 200);
  assert.deepEqual(
    result.checks.map(({ key, status, records }) => ({ key, status, records })),
    [
      { key: "diary", status: "available", records: 4706 },
      { key: "finance", status: "available", records: 48 },
      { key: "representatives", status: "available", records: 19 },
    ],
  );
});

test("saúde pública informa degradação sem transformar uma fonte ausente em zero", () => {
  const result = buildOperationalHealth({
    checkedAt: "2026-08-31T12:00:00.000Z",
    diary: { state: "available", records: 4706 },
    finance: { state: "unavailable" },
    representatives: { state: "available", records: 19 },
  });

  assert.equal(result.status, "degraded");
  assert.equal(result.httpStatus, 200);
  assert.equal(result.checks[1].records, null);
});

test("saúde pública retorna 503 quando nenhum domínio pode ser verificado", () => {
  const result = buildOperationalHealth({
    checkedAt: "2026-08-31T12:00:00.000Z",
    diary: { state: "unavailable" },
    finance: { state: "unavailable" },
    representatives: { state: "unavailable" },
  });

  assert.equal(result.status, "unavailable");
  assert.equal(result.httpStatus, 503);
  assert.equal(result.checks.every((check) => check.records === null), true);
});

test("rota de saúde é dinâmica e consulta os domínios públicos reais", async () => {
  const source = await readFile(
    new URL("../app/api/health/route.ts", import.meta.url),
    "utf8",
  );

  assert.match(source, /dynamic\s*=\s*["']force-dynamic["']/);
  assert.match(source, /getOfficialDiaryCatalog/);
  assert.match(source, /getPublicFinanceCoverage/);
  assert.match(source, /getMunicipalCouncillors/);
  assert.doesNotMatch(source, /status:\s*["']ok["']/);
});
