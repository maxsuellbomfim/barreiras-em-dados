import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260812211202_parliamentary_transfer_rankings.sql",
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

test("ranking separa autoria individual de comissoes e bancadas", () => {
  assert.match(migration, /author_scope not in \('person', 'collective'\)/);
  assert.match(migration, /transfer\.author_kind = 'person'/);
  assert.match(migration, /'commission', 'bench', 'collective'/);
  assert.match(client, /author_scope: "person"/);
  assert.match(client, /author_scope: "collective"/);
  assert.match(page, /Parlamentares que destinaram recursos/);
  assert.match(page, /Comiss/);
});

test("ranking usa valores oficiais sem produzir nota subjetiva de desempenho", () => {
  assert.match(migration, /paid_amount desc nulls last/);
  assert.match(migration, /destination_amount desc/);
  assert.match(page, /N.o . uma nota geral de desempenho/);
  assert.match(page, /n.o mede leis, fiscaliza/);
  assert.doesNotMatch(migration, /score|pontua/iu);
});

test("emenda publica mantem autor, estagios e evidencia verificavel", () => {
  assert.match(migration, /origin_distribution_raw_record_id/);
  assert.match(migration, /origin_proposal_raw_record_id/);
  assert.match(migration, /artifact\.sha256 as artifact_sha256/);
  assert.match(client, /artifactSha256/);
  assert.match(page, /Valor destinado/);
  assert.match(page, /Valor empenhado/);
  assert.match(page, /Valor pago confirmado/);
  assert.match(page, /Abrir registro oficial no Transferegov/);
});

test("dado financeiro ausente nunca aparece como zero", () => {
  assert.match(page, /n.o foi encontrado nos endpoints oficiais/);
  assert.match(page, /nunca que o valor . zero/);
  assert.match(page, /Pagamento n.o encontrado nos endpoints consultados/);
});

test("cliente aceita decimais numericos do PostgREST sem perder centavos", () => {
  assert.match(client, /typeof value === "number"/);
  assert.match(client, /Number\.isFinite\(value\)/);
  assert.match(client, /Number\.isSafeInteger\(roundedCents\)/);
  assert.match(client, /normalizedValue\.toFixed\(2\)/);
});
