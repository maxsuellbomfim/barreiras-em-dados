import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260813185756_public_bahia_state_loa_amendments.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(
  new URL("../../apps/web/lib/parliamentary-transfers.ts", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

test("projecao publica aceita somente extracoes validadas e rastreaveis", () => {
  assert.match(migration, /bahia_state_loa_authorized_amendment/);
  assert.match(migration, /bahia-state-loa-barreiras\/1\.1\.0/);
  assert.match(migration, /validation_status = 'valid'/);
  assert.match(migration, /job\.status = 'succeeded'/);
  assert.match(migration, /financial_stage[^\n]+authorized/);
  assert.match(migration, /source_artifact_sha256[^\n]+\^\[0-9a-f\]\{64\}\$/);
  assert.match(migration, /evidence_sha256[^\n]+\^\[0-9a-f\]\{64\}\$/);
});

test("RPCs publicas ocultam tabelas brutas e limitam parametros", () => {
  assert.match(migration, /get_public_bahia_state_loa_amendments/);
  assert.match(migration, /get_public_bahia_state_loa_amendment_ranking/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(migration, /revoke all on territory\.bahia_state_loa_amendments/);
  assert.match(migration, /page_size[^\n]+> 200/);
  assert.match(migration, /grant execute[^;]+to anon, authenticated/s);
  assert.doesNotMatch(migration, /grant select[^;]+raw\.extraction/);
});

test("site separa autorizacao orcamentaria estadual de pagamento e execucao", () => {
  assert.match(client, /get_public_bahia_state_loa_amendments/);
  assert.match(client, /get_public_bahia_state_loa_amendment_ranking/);
  assert.match(client, /financialStage: "authorized"/);
  assert.match(page, /Emendas estaduais autorizadas na LOA/);
  assert.match(page, /autorizad[oa] no or.amento/i);
  assert.match(page, /n.o significa dinheiro pago/);
  assert.match(page, /Abrir anexo oficial da LOA/);
  assert.match(page, /N.o . nota de desempenho/);
  assert.doesNotMatch(page, /pontua..o/iu);
});
