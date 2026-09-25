import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const component = read("apps/admin/app/commitment-link-review.tsx");
const page = read("apps/admin/app/page.tsx");
const queue = read(
  "supabase/migrations/20260924090843_commitment_link_review_queue.sql",
).replace(/--[^\n]*/g, "");
const publicLinks = read(
  "supabase/migrations/20260924092113_public_links_include_human_review.sql",
).replace(/--[^\n]*/g, "");

test("fila e decisão exigem revisor ativo e nunca ficam abertas ao anon", () => {
  for (const fn of ["get_commitment_link_review_groups", "review_commitment_link_group"]) {
    const body = queue.slice(queue.indexOf(`function api.${fn}(`));
    assert.match(body.slice(0, 2000), /if not api\.is_active_reviewer\(\) then/);
    assert.match(queue, new RegExp(`revoke all on function api\\.${fn}\\([^)]*\\)\\s+from public, anon;`));
    assert.match(queue, new RegExp(`grant execute on function api\\.${fn}\\([^)]*\\)\\s+to authenticated;`));
  }
});

test("a decisão é gravada por ligação, com justificativa e contrato candidato", () => {
  assert.match(queue, /length\(btrim\(coalesce\(p_review_note, ''\)\)\) < 5/);
  assert.match(queue, /\(p_review_decision = 'approved'\) <> \(p_contract_raw_record_id is not null\)/);
  assert.match(queue, /candidate\.contract_raw_record_id = p_contract_raw_record_id/);
  assert.match(queue, /if eligible <> expected then/);
  assert.match(queue, /insert into editorial\.editorial_reviews \(/);
  assert.match(queue, /'finance\.commitment_contract_links',\s*link\.id,/);
  // Pedido de evidência não tira o item da fila; aprovar ou rejeitar, sim.
  assert.match(queue, /in \('pending', 'changes_requested'\)/);
  assert.match(queue, /create trigger reject_mutation\s+before update or delete on finance\.commitment_link_candidates/);
});

test("a projeção pública só inclui humano com última revisão aprovada", () => {
  assert.match(publicLinks, /'human'::text as review_mode/);
  assert.match(publicLinks, /review\.decision = 'approved'/);
  assert.match(publicLinks, /link\.state = 'citacao_sem_confirmacao'/);
  assert.match(publicLinks, /\) = 'approved'/);
  assert.match(publicLinks, /\) <> 'withdrawn'/);
  assert.doesNotMatch(publicLinks, /\bsum\(/i);
});

test("o painel confirma só com contrato escolhido e justificativa", () => {
  assert.match(component, /"get_commitment_link_review_groups"/);
  assert.match(component, /"review_commitment_link_group"/);
  assert.match(component, /disabled=\{busy \|\| !noteReady \|\| selected === null\}/);
  assert.match(component, /p_contract_raw_record_id: decision === "approved" \? contractRawRecordId : null/);
  assert.match(component, /revisores ativos/);
  assert.match(page, /<CommitmentLinkReview rpc=\{rpc\} \/>/);
  assert.match(page, /Empenhos × contratos/);
});

test("a fila vigente agrupa sem carregar o payload inteiro e limita antes das amostras", () => {
  const slim = read("supabase/migrations/20260924092958_review_groups_slim_cte.sql").replace(
    /--[^\n]*/g,
    "",
  );
  const pending = slim.slice(slim.indexOf("with pending as materialized"), slim.indexOf("groups as ("));
  assert.doesNotMatch(pending, /record\.payload,/);
  assert.match(pending, /record\.payload ->> 'field1144629' as creditor_name/);
  assert.ok(slim.indexOf("page as (") < slim.indexOf("from page as grouped"));
  assert.match(slim, /if not api\.is_active_reviewer\(\) then/);
});
