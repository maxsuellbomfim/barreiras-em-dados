import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const representativesPage = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);

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
const aliasCommand = await readFile(
  new URL(
    "../../workers/document-processing/src/barreiras_docproc/commands/suggest_representative_aliases.py",
    import.meta.url,
  ),
  "utf8",
);
const aliasRepository = await readFile(
  new URL(
    "../../workers/document-processing/src/barreiras_docproc/alias_repository.py",
    import.meta.url,
  ),
  "utf8",
);
const aliasIndexes = await readFile(
  new URL(
    "../../supabase/migrations/20260808170000_alias_assist_query_indexes.sql",
    import.meta.url,
  ),
  "utf8",
);
const aliasReviewFix = await readFile(
  new URL(
    "../../supabase/migrations/20260808190000_fix_alias_review_note_rpc.sql",
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

test("cota esgotada usa regras locais e continua pendente", () => {
  assert.match(aliasAssist, /classify_alias_deterministically/);
  assert.match(aliasAssist, /first_and_surname/);
  assert.match(aliasCommand, /using_local_rules/);
  assert.match(aliasCommand, /provider = "local"/);
  assert.match(aliasCommand, /persist_suggestion/);
});

test("fila de aliases tem consulta limitada e evita multiplicação cartesiana", () => {
  assert.match(aliasRepository, /set statement_timeout = '30s'/);
  assert.match(aliasRepository, /candidate_options/);
  assert.match(aliasRepository, /historical_options/);
  assert.doesNotMatch(aliasRepository, /cross join candidates/);
  assert.match(aliasIndexes, /raw_records_alias_assist_type_idx/);
  assert.match(aliasIndexes, /raw_records_alias_assist_author_idx/);
});

test("revisão de alias não confunde parâmetro e coluna review_note", () => {
  assert.match(aliasReviewFix, /drop function if exists api\.review_representative_alias_suggestion/);
  assert.match(aliasReviewFix, /p_review_note text default null/);
  assert.match(aliasReviewFix, /review_note = nullif\(btrim\(p_review_note\), ''\)/);
  assert.match(aliasReviewFix, /update political\.representative_alias_suggestions as suggestion_row/);
});

test("perfil federal recebe resumo de emendas somente por identificador aprovado", () => {
  assert.match(representativesPage, /getPublicParliamentaryTransferRankings/);
  assert.match(representativesPage, /transferSummaryForRepresentative/);
  assert.match(representativesPage, /Recursos destinados a Barreiras/);
  assert.match(representativesPage, /id={`federal-\${person\.externalId}`}/);
});
