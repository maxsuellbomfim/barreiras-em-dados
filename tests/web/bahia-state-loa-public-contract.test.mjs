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
const executionMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260814111419_publish_bahia_state_loa_execution.sql",
    import.meta.url,
  ),
  "utf8",
);
const historicalExecutionMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260814124500_explain_historical_bahia_state_loa_linkage.sql",
    import.meta.url,
  ),
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
  assert.match(client, /get_public_bahia_state_loa_study/);
  assert.match(client, /get_public_bahia_state_loa_amendment_ranking/);
  assert.match(client, /financialStage: "authorized"/);
  assert.match(page, /Emendas estaduais autorizadas na LOA/);
  assert.match(page, /autorizad[oa] no or.amento/i);
  assert.match(page, /n.o significa dinheiro pago/);
  assert.match(page, /Abrir anexo oficial da LOA/);
  assert.match(page, /N.o . nota de desempenho/);
  assert.doesNotMatch(page, /pontua..o/iu);
});

test("ranking estadual separa autoria historica do perfil oficial atual", () => {
  assert.match(client, /representativeSourceKind/);
  assert.match(client, /representativeExternalId/);
  assert.match(client, /representativeProfileUrl/);
  assert.match(client, /associationStatus/);
  assert.match(page, /Perfil oficial dispon.vel/);
  assert.match(page, /perfil pode ser de outra Casa/);
  assert.match(page, /Perfil atual ainda n.o confirmado/);
  assert.match(page, /\/representantes#\$\{row\.representativeSourceKind\}-/);
  assert.doesNotMatch(page, /row\.representativeSourceKind === "state"/);
});

test("execucao estadual publica somente ligacoes unicas e explica a cobertura", () => {
  assert.match(executionMigration, /get_public_bahia_state_loa_execution/);
  assert.match(executionMigration, /matched_bidirectional_unique/);
  assert.match(executionMigration, /ambiguous_official_key/);
  assert.match(executionMigration, /security definer/);
  assert.match(executionMigration, /revoke all[^;]+from public/s);
  assert.match(client, /parseStateLoaExecutionRows/);
  assert.match(client, /get_public_bahia_state_loa_execution_summary/);
  assert.match(page, /O que aconteceu com as/);
  assert.match(page, /universo compar.vel aos est.gios abaixo/iu);
  assert.match(page, /n.o devem ser comparados diretamente/iu);
  assert.doesNotMatch(page, /ranking de pagamento/iu);
});

test("emendas historicas recebem diagnostico explicito sem fabricar execucao", () => {
  assert.match(historicalExecutionMigration, /blocked_scope_year_not_indexed/);
  assert.match(historicalExecutionMigration, /official_link_key_unavailable/);
  assert.match(
    historicalExecutionMigration,
    /bahia-state-loa-public-execution\/1\.1\.0/,
  );
  assert.match(
    client,
    /get_public_bahia_state_loa_study[\s\S]+fiscal_year_filter: stateFiscalYear/,
  );
  assert.match(page, /identificadores necess.rios/iu);
});

test("site explica a ausencia de municipio e liga o diagrama oficial", () => {
  assert.match(page, /Como a Bahia relaciona os dados/);
  assert.match(page, /arquivo de execu..o n.o publica munic.pio/iu);
  assert.match(
    page,
    /https:\/\/dados\.ba\.gov\.br\/dataset\/1436b3e7-6594-4683-bfa5-b2e3a6c69e07\/resource\/f463ff7d-569c-4b48-b1d3-c80f017779df\/download\/emendas-parlamentares-relacionamento_views\.png/,
  );
  assert.match(page, /Abrir diagrama oficial das rela..es/iu);
});

test("filtro anual estadual mantém ranking, emendas e execução no mesmo período", () => {
  assert.match(
    client,
    /getPublicParliamentaryTransfers\([\s\S]*stateFiscalYear/,
  );
  assert.doesNotMatch(client, /stateFiscalYear\s*=\s*2026/);
  assert.match(
    client,
    /get_public_bahia_state_loa_study[\s\S]+fiscal_year_filter:\s*stateFiscalYear/,
  );
  assert.match(
    client,
    /get_public_bahia_state_loa_amendment_ranking[\s\S]+fiscal_year_filter:\s*stateFiscalYear/,
  );
  assert.match(client, /parseStateLoaExecutionRows\(\[\.\.\.stateLoaStudy\.executionRows\]\)/);
  assert.match(
    page,
    /aria-label="Filtrar emendas estaduais por ano"/,
  );
  assert.match(page, /name="origem" value="estadual"/);
  assert.match(page, /Resumo de \{selectedFiscalYear\}/);
  assert.match(
    page,
    /Recursos estaduais[^\n]+\{selectedFiscalYear\}/,
  );
  assert.doesNotMatch(page, /Para 2026, os est.gios/iu);
});
