import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260813133500_public_historical_parliamentary_amendments.sql",
    import.meta.url,
  ),
  "utf8",
);
const territorialScopeMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260813140050_strict_barreiras_transfer_scope.sql",
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

test("emendas historicas preservam autoria, proposta e evidencia oficial", () => {
  assert.match(migration, /transferegov_historical_amendment/);
  assert.match(migration, /origin_amendment_raw_record_id/);
  assert.match(migration, /origin_proposal_raw_record_id/);
  assert.match(migration, /artifact\.sha256 as artifact_sha256/);
  assert.match(migration, /valor_repasse_emenda/);
  assert.match(client, /get_public_historical_parliamentary_amendments/);
  assert.match(page, /Emendas identificadas no acervo hist.rico/);
  assert.match(page, /Abrir arquivo oficial no Transferegov/);
});

test("ranking historico separa parlamentar de autoria coletiva", () => {
  assert.match(migration, /author_scope not in \('person', 'collective'\)/);
  assert.match(migration, /author_kind = 'person'/);
  assert.match(migration, /'commission', 'bench', 'collective'/);
  assert.match(client, /get_public_historical_parliamentary_amendment_ranking/);
  assert.match(page, /Ranking hist.rico de autoria individual/);
  assert.match(page, /Autoria coletiva no acervo hist.rico/);
});

test("historico nao confunde valor destinado com pagamento", () => {
  assert.match(migration, /'destination_identified_payment_not_verified'/);
  assert.match(page, /n.o comprova empenho, pagamento nem execu..o/);
  assert.match(page, /Valor destinado . proposta/);
  assert.doesNotMatch(migration, /score|pontua/iu);
});

test("projecao publica minimiza dados pessoais e fecha acesso direto", () => {
  assert.match(migration, /revoke all on territory\.historical_parliamentary_amendments/);
  assert.match(migration, /grant execute on function api\.get_public_historical/);
  assert.doesNotMatch(migration, /beneficiario_ultimos_4/);
  assert.doesNotMatch(migration, /beneficiario_identificador/);
  assert.doesNotMatch(migration, /cpf|cnpj/iu);
});

test("falha transitória do cache da RPC recebe uma tentativa sem cache", () => {
  assert.match(client, /fetchPublicRpcRows/);
  assert.doesNotMatch(client, /AbortSignal\.timeout\(5_000\)/);
});

test("recorte territorial nao atribui projetos regionais a Barreiras", () => {
  assert.match(territorialScopeMigration, /federal_transfer_proposal_scope/);
  assert.match(territorialScopeMigration, /object_explicitly_mentions_barreiras/);
  assert.match(territorialScopeMigration, /regional_entity_destination_unverified/);
  assert.match(territorialScopeMigration, /recipient_registered_in_barreiras/);
  assert.match(territorialScopeMigration, /is_confirmed_for_barreiras/);
  assert.match(territorialScopeMigration, /get_public_federal_transfer_scope_summary/);
  assert.doesNotMatch(territorialScopeMigration, /delete\s+from\s+raw\./iu);
  assert.match(client, /get_public_federal_transfer_scope_summary/);
  assert.match(page, /n.o atribu.dos a Barreiras/);
  assert.match(page, /cons.rcio regional/);
});
