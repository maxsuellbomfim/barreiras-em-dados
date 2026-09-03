import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ACTIVE = path.join(ROOT, "supabase", "migrations");
const LEGACY = path.join(
  ROOT,
  "docs",
  "operations",
  "supabase-migrations-legacy",
  "2026-09-03",
);

const reconciledMigrations = [
  [
    "20260902213010_optimize_executive_profiles_rpc.sql",
    "20260902213713_optimize_executive_profiles_rpc.sql",
  ],
  [
    "20260902220000_tse_votes_server_pagination.sql",
    "20260902220621_tse_votes_server_pagination.sql",
  ],
  [
    "20260902225721_cgu_document_study_pagination.sql",
    "20260902230614_cgu_document_study_pagination.sql",
  ],
  [
    "20260902233000_paginate_bahia_state_loa_study.sql",
    "20260903013926_paginate_bahia_state_loa_study.sql",
  ],
  [
    "20260903023000_filter_bahia_state_loa_study.sql",
    "20260903020620_filter_bahia_state_loa_study.sql",
  ],
  [
    "20260903030000_match_all_state_loa_search_terms.sql",
    "20260903021021_match_all_state_loa_search_terms.sql",
  ],
];

function normalizeSql(value) {
  return value.replaceAll("\r\n", "\n").trim();
}

test("active migrations use the six versions recorded by Supabase", async () => {
  for (const [legacyName, remoteName] of reconciledMigrations) {
    const legacyPath = path.join(LEGACY, legacyName);
    const staleActivePath = path.join(ACTIVE, legacyName);
    const canonicalPath = path.join(ACTIVE, remoteName);

    assert.equal(
      existsSync(staleActivePath),
      false,
      `${legacyName} must not remain active under an unapplied version`,
    );
    assert.equal(existsSync(legacyPath), true, `${legacyName} must be archived`);
    assert.equal(
      existsSync(canonicalPath),
      true,
      `${remoteName} must be the active canonical migration`,
    );
    assert.equal(
      normalizeSql(await readFile(canonicalPath, "utf8")),
      normalizeSql(await readFile(legacyPath, "utf8")),
      `${remoteName} must preserve the reviewed SQL exactly`,
    );
  }
});
