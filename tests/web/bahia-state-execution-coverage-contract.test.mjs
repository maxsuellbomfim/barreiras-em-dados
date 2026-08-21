import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parseBahiaStateExecutionCoverageRows,
} from "../../apps/web/lib/bahia-state-execution-coverage.mjs";

const migration = readFileSync(
  new URL(
    "../../supabase/migrations/20260821170000_publish_bahia_state_execution_annual_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);
const panel = readFileSync(
  new URL(
    "../../apps/web/app/recursos/bahia-state-execution-coverage-panel.tsx",
    import.meta.url,
  ),
  "utf8",
);
const methodology = readFileSync(
  new URL("../../docs/PARLIAMENTARY_TRANSFERS_METHODOLOGY.md", import.meta.url),
  "utf8",
);

function row(overrides = {}) {
  return {
    fiscal_year: 2026,
    source_aggregate_count: 933,
    source_author_count: 65,
    territorial_key_status: "territorial_key_unavailable_in_source",
    source_snapshot_status: "source_snapshot_observed",
    source_url: "https://dados.ba.gov.br/dataset/emendas-parlamentares",
    source_artifact_sha256: "a".repeat(64),
    source_collected_at: "2026-08-21T12:00:00+00:00",
    methodology_version: "bahia-state-execution-source-coverage/1.0.0",
    ...overrides,
  };
}

test("parser conserva somente contagens anuais e linhagem pública", () => {
  const parsed = parseBahiaStateExecutionCoverageRows([
    row(),
    row({
      fiscal_year: 2025,
      source_aggregate_count: 922,
      source_author_count: 63,
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].fiscalYear, 2026);
  assert.equal(parsed[0].sourceAggregateCount, 933);
  assert.equal(parsed[1].sourceAuthorCount, 63);
  assert.equal(JSON.stringify(parsed).includes("amount"), false);
});

test("parser rejeita escopo inventado, hash inválido e anos duplicados", () => {
  assert.equal(
    parseBahiaStateExecutionCoverageRows([
      row({ territorial_key_status: "barreiras_confirmed" }),
    ]),
    null,
  );
  assert.equal(
    parseBahiaStateExecutionCoverageRows([
      row({ source_artifact_sha256: "invalido" }),
    ]),
    null,
  );
  assert.equal(parseBahiaStateExecutionCoverageRows([row(), row()]), null);
});

test("migration fecha acesso direto e expõe apenas RPC sanitizada", () => {
  assert.match(migration, /force row level security/);
  assert.match(migration, /api\.get_public_bahia_state_execution_annual_coverage/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(migration, /territorial_key_unavailable_in_source/);
  assert.doesNotMatch(migration, /returns table[\s\S]*paid_amount/);
});

test("página diferencia cobertura estadual de destinação municipal", () => {
  assert.match(panel, /Cobertura do arquivo estadual de execução/);
  assert.match(panel, /não informa o município/);
  assert.match(panel, /não\s+são valores destinados a Barreiras/);
  assert.match(page, /getPublicBahiaStateExecutionCoverage/);
  assert.match(
    methodology,
    /bahia-state-execution-source-coverage\/1\.0\.0/,
  );
});
