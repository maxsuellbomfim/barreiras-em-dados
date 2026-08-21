import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parseStateAmendmentSourceCoverageRows,
} from "../../apps/web/lib/state-amendment-source-coverage.mjs";

const migration = readFileSync(
  new URL(
    "../../supabase/migrations/20260821034625_public_state_amendment_source_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);
const historicalKeyGapMigration = readFileSync(
  new URL(
    "../../supabase/migrations/20260821183000_explain_historical_state_execution_key_gap.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);
const methodology = readFileSync(
  new URL("../../docs/PARLIAMENTARY_TRANSFERS_METHODOLOGY.md", import.meta.url),
  "utf8",
);

function row(overrides = {}) {
  return {
    fiscal_year: 2026,
    loa_status: "observed",
    amendment_count: 34,
    author_count: 7,
    authorized_amount: "11198888.00",
    execution_status: "partial",
    matched_count: 10,
    ambiguous_count: 21,
    not_found_count: 3,
    unavailable_scope_count: 0,
    committed_amount: "349933.00",
    liquidated_amount: "329933.00",
    paid_amount: "329933.00",
    last_attempted_at: "2026-08-20T05:44:22.190847+00:00",
    source_url: "https://www.ba.gov.br/seplan/orcamento/historico-de-loa",
    methodology_version: "state-amendment-source-coverage/1.0.0",
    ...overrides,
  };
}

test("parser conserva ausência financeira e aceita bloqueio oficial", () => {
  const parsed = parseStateAmendmentSourceCoverageRows([
    row(),
    row({
      fiscal_year: 2025,
      amendment_count: 7,
      author_count: 4,
      authorized_amount: "997600.00",
      execution_status: "scope_not_indexed",
      matched_count: 0,
      ambiguous_count: 0,
      not_found_count: 0,
      unavailable_scope_count: 7,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
    }),
    row({
      fiscal_year: 2021,
      loa_status: "blocked",
      amendment_count: null,
      author_count: null,
      authorized_amount: null,
      execution_status: "loa_unavailable",
      matched_count: null,
      ambiguous_count: null,
      not_found_count: null,
      unavailable_scope_count: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[1].paidAmount, null);
  assert.equal(parsed[2].loaStatus, "blocked");
  assert.equal(parsed[2].authorizedAmount, null);
});

test("parser distingue ausência de chave oficial de escopo ainda não indexado", () => {
  const parsed = parseStateAmendmentSourceCoverageRows([
    row({
      fiscal_year: 2025,
      amendment_count: 7,
      author_count: 4,
      authorized_amount: "997600.00",
      execution_status: "blocked_missing_official_key",
      matched_count: null,
      ambiguous_count: null,
      not_found_count: null,
      unavailable_scope_count: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      methodology_version: "state-amendment-source-coverage/1.1.0",
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].executionStatus, "blocked_missing_official_key");
  assert.equal(parsed[0].paidAmount, null);

  assert.equal(
    parseStateAmendmentSourceCoverageRows([
      row({
        fiscal_year: 2025,
        amendment_count: 7,
        author_count: 4,
        authorized_amount: "997600.00",
        execution_status: "blocked_missing_official_key",
        matched_count: 0,
        ambiguous_count: 0,
        not_found_count: 0,
        unavailable_scope_count: 7,
        committed_amount: null,
        liquidated_amount: null,
        paid_amount: null,
        methodology_version: "state-amendment-source-coverage/1.1.0",
      }),
    ]),
    null,
  );
});

test("parser aceita decimais numéricos enviados pelo PostgREST", () => {
  const parsed = parseStateAmendmentSourceCoverageRows([
    row({
      authorized_amount: 11198888,
      committed_amount: 349933,
      liquidated_amount: 329933,
      paid_amount: 329933,
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].authorizedAmount, "11198888.00");
  assert.equal(parsed[0].paidAmount, "329933.00");
  assert.equal(
    parseStateAmendmentSourceCoverageRows([
      row({ authorized_amount: 1.001 }),
    ]),
    null,
  );
});

test("parser rejeita zero fabricado, HTTP e anos duplicados", () => {
  assert.equal(
    parseStateAmendmentSourceCoverageRows([
      row({ loa_status: "blocked", authorized_amount: "0.00" }),
    ]),
    null,
  );
  assert.equal(
    parseStateAmendmentSourceCoverageRows([
      row({ source_url: "http://example.test/loa" }),
    ]),
    null,
  );
  assert.equal(parseStateAmendmentSourceCoverageRows([row(), row()]), null);
});

test("migration publica somente agregado anual sanitizado", () => {
  assert.match(migration, /api\.get_public_state_amendment_source_coverage/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(migration, /revoke all on function[\s\S]+from public/);
  assert.match(migration, /grant execute on function[\s\S]+to anon, authenticated/);
  assert.doesNotMatch(migration, /checkpoint\s+jsonb/);
  assert.doesNotMatch(migration, /block_reason\s+text/);
  assert.doesNotMatch(migration, /error_detail/);
});

test("migration histórica classifica a lacuna documental sem fabricar contagens", () => {
  assert.match(
    historicalKeyGapMigration,
    /blocked_missing_official_key/,
  );
  assert.match(
    historicalKeyGapMigration,
    /state-amendment-source-coverage\/1\.1\.0/,
  );
  assert.match(historicalKeyGapMigration, /between 2022 and 2025/);
  assert.doesNotMatch(historicalKeyGapMigration, /similarity\s*\(/i);
});

test("página explica cobertura estadual sem inventar pagamento", () => {
  assert.match(page, /Quais anos estaduais já foram conferidos/);
  assert.match(page, /link rotulado como 2021 aponta para o anexo de 2020/);
  assert.match(page, /não é R\$ 0/);
  assert.match(page, /não publica os códigos necessários/);
  assert.match(page, /não significa que o recurso não foi executado/);
  assert.match(page, /getPublicStateAmendmentSourceCoverage/);
  assert.match(methodology, /state-amendment-source-coverage\/1\.1\.0/);
});
