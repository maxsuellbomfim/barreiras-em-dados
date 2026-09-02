import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildOperationalHealth,
  combineRepresentationHealthProbes,
} from "./operational-health.mjs";

test("representação só fica disponível quando as quatro fontes respondem", () => {
  assert.deepEqual(
    combineRepresentationHealthProbes([
      { state: "available", records: 19 },
      { state: "available", records: 15 },
      { state: "available", records: 63 },
      { state: "available", records: 39 },
    ]),
    { state: "available", records: 136 },
  );

  assert.deepEqual(
    combineRepresentationHealthProbes([
      { state: "available", records: 19 },
      { state: "unavailable" },
      { state: "available", records: 63 },
      { state: "available", records: 39 },
    ]),
    { state: "unavailable" },
  );

  assert.deepEqual(
    combineRepresentationHealthProbes([
      { state: "available", records: 19 },
      { state: "available", records: 15 },
      { state: "available", records: 0 },
      { state: "available", records: 39 },
    ]),
    { state: "unavailable" },
  );
});

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

test("rota de saúde é dinâmica e reutiliza a fotografia dos domínios reais", async () => {
  const [source, snapshot] = await Promise.all([
    readFile(new URL("../app/api/health/route.ts", import.meta.url), "utf8"),
    readFile(new URL("./operational-health-snapshot.ts", import.meta.url), "utf8"),
  ]);

  assert.match(source, /dynamic\s*=\s*["']force-dynamic["']/);
  assert.match(source, /getOperationalHealthSnapshot/);
  assert.doesNotMatch(source, /status:\s*["']ok["']/);
  assert.match(snapshot, /getIntegralGazetteEditions/);
  assert.match(snapshot, /getIntegralGazetteEditions\(\{ pageSize: 1 \}\)/);
  assert.doesNotMatch(snapshot, /getOfficialDiaryCatalog/);
  assert.match(snapshot, /getPublicFinanceCoverage/);
  assert.match(snapshot, /getMunicipalCouncillors/);
  assert.match(snapshot, /getExecutiveProfiles/);
  assert.match(snapshot, /getStateRepresentatives/);
  assert.match(snapshot, /getFederalRepresentatives/);
  assert.match(snapshot, /combineRepresentationHealthProbes/);
});
