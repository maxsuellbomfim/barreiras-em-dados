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
const authorLinkMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260812224207_link_parliamentary_transfer_authors_to_profiles.sql",
    import.meta.url,
  ),
  "utf8",
);
const coverageMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260813004926_public_parliamentary_transfer_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);
const historicalProposalMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260813112804_public_federal_transfer_proposals.sql",
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

test("autoria individual aprovada liga ranking e perfil oficial por identificador", () => {
  assert.match(authorLinkMigration, /representative_external_id/);
  assert.match(authorLinkMigration, /approved_official_crosswalk/);
  assert.match(client, /representativeExternalId/);
  assert.match(client, /associationStatus/);
  assert.match(page, /Ver perfil, votos e mandato/);
  assert.match(page, /\/representantes#\$\{row\.representativeSourceKind/);
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

test("cobertura anual distingue vazio confirmado de ano ainda nao classificado", () => {
  assert.match(coverageMigration, /coalesce\(annual\.status, 'unclassified'\)/);
  assert.match(coverageMigration, /annual\.status = 'empty' then 0/);
  assert.match(client, /get_public_parliamentary_transfer_coverage/);
  assert.match(client, /coverage: readonly ParliamentaryTransferCoverage\[\] \| null/);
  assert.match(page, /Quais anos j. conferimos/);
  assert.match(page, /n.o prova aus.ncia em outras bases\s+oficiais/);
  assert.match(page, /Coleta incompleta/);
  assert.match(page, /Ano ainda n.o classificado/);
});

test("propostas historicas ficam separadas de emendas e exibem seus limites", () => {
  assert.match(historicalProposalMigration, /transferegov_historical_proposal/);
  assert.match(historicalProposalMigration, /not_available_in_proposal_source/);
  assert.match(historicalProposalMigration, /proposal_registered/);
  assert.match(historicalProposalMigration, /artifact\.sha256 as artifact_sha256/);
  assert.match(historicalProposalMigration, /revoke all on territory\.federal_transfer_proposals/);
  assert.match(client, /get_public_federal_transfer_proposals/);
  assert.match(client, /FederalTransferProposal/);
  assert.match(page, /Propostas federais encontradas desde 2021/);
  assert.match(page, /proposta n.o significa dinheiro pago/);
  assert.match(page, /Autoria parlamentar n.o dispon.vel nesta fonte/);
  assert.match(page, /Arquivo oficial completo no Transferegov/);
  assert.match(page, /ficha de proposta, isoladamente, n.o entra no ranking/);
  assert.match(page, /arquivo oficial de emendas comprova autor e valor destinado/);
});
