import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260808150000_representative_alias_review.sql",
    import.meta.url,
  ),
  "utf8",
);
const workflow = await readFile(
  new URL(
    "../../.github/workflows/suggest-representative-aliases.yml",
    import.meta.url,
  ),
  "utf8",
);
const aliasAssist = await readFile(
  new URL(
    "../../workers/document-processing/src/barreiras_docproc/alias_assist.py",
    import.meta.url,
  ),
  "utf8",
);

test("aliases de representantes ficam pendentes e auditáveis", () => {
  assert.match(migration, /representative_alias_suggestions/);
  assert.match(migration, /status in \('pending', 'accepted', 'rejected', 'needs_more_evidence'\)/);
  assert.match(migration, /api\.review_representative_alias_suggestion/);
  assert.match(migration, /api\.is_active_reviewer\(\)/);
  assert.match(migration, /revoke all on table political\.representative_alias_suggestions/);
});

test("a cascata de aliases usa mundo fechado e não publica", () => {
  assert.match(aliasAssist, /candidate_external_id deve ser exatamente/);
  assert.match(aliasAssist, /revisão humana/);
  assert.match(aliasAssist, /run_cascade_content/);
  assert.match(workflow, /suggest_representative_aliases/);
  assert.match(workflow, /sem publicação automática/);
});

