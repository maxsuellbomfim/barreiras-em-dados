import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

const migrations = new URL("../../supabase/migrations/", import.meta.url);
const migrationName = (await readdir(migrations)).find((name) =>
  name.endsWith("_act_quality_sample.sql"),
);
const sql = await readFile(new URL(migrationName, migrations), "utf8");
const component = await readFile(
  new URL("../../apps/admin/app/act-quality-review.tsx", import.meta.url),
  "utf8",
);
const page = await readFile(new URL("../../apps/admin/app/page.tsx", import.meta.url), "utf8");

test("RPCs da amostra só atendem revisores ativos e nunca anônimos", () => {
  for (const fn of [
    "api.get_act_quality_sample()",
    "api.annotate_act_quality_page(",
    "api.get_act_quality_metrics()",
  ]) {
    const body = sql.slice(sql.indexOf(`create function ${fn}`));
    assert.match(body.slice(0, 2500), /if not api\.is_active_reviewer\(\) then/, fn);
  }
  assert.match(sql, /revoke all on function api\.get_act_quality_sample\(\) from public, anon;/);
  assert.match(sql, /grant execute on function api\.get_act_quality_metrics\(\) to authenticated;/);
});

test("anotação é append-only e separada das decisões de publicação", () => {
  assert.match(sql, /'editorial\.act_quality_annotations'/);
  assert.match(sql, /create trigger reject_mutation before update or delete on %s/);
  const annotate = sql.slice(sql.indexOf("create function api.annotate_act_quality_page"));
  assert.doesNotMatch(
    annotate.slice(0, annotate.indexOf("$$;")),
    /editorial_reviews/,
    "medir qualidade não pode mexer no que está publicado",
  );
  assert.match(annotate, /cada ato da página precisa de exatamente um veredito/);
});

test("página do ato só vale quando o texto remontado reproduz o hash do ato", () => {
  assert.match(sql, /if rebuilt_sha = artifact\.canonical_sha then/);
  assert.match(sql, /'unverified_artifacts', unverified_artifacts/);
  assert.match(sql, /E'\\n\\n' order by parts\.page_number/);
});

test("sorteio reproduzível pela semente e trechos com CPF mascarado", () => {
  assert.match(sql, /p_seed \|\| ':' \|\| eligible\.sha256 \|\| ':' \|\| strata\.page_number::text/);
  assert.match(sql, /editorial\.mask_cpf_v1\(result\.result_payload ->> 'excerpt'\)/);
  assert.match(sql, /'act-quality-metrics\/1\.0\.0'/);
});

test("aba do admin usa as RPCs e trata acesso negado", () => {
  assert.match(component, /rpc\("get_act_quality_sample"/);
  assert.match(component, /rpc\("get_act_quality_metrics"/);
  assert.match(component, /rpc\("annotate_act_quality_page"/);
  assert.match(component, /revisores ativos/);
  assert.match(component, /disabled=\{busy \|\| !complete\}/);
  assert.match(page, /<ActQualityReview rpc=\{rpc\} \/>/);
  assert.match(page, /Qualidade dos atos/);
});
