import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);

test("arquivo histórico de emendas exige opt-in e depende das propostas preservadas", () => {
  const transferegovJob = workflow.slice(workflow.indexOf("  transferegov:"));

  assert.match(workflow, /include_transferegov_historical_amendments:/);
  assert.match(
    transferegovJob,
    /if: github\.event_name == 'workflow_dispatch' && inputs\.include_transferegov_historical_amendments == true/,
  );
  assert.match(
    transferegovJob,
    /barreiras_collectors\.commands\.collect_transferegov_historical_amendments/,
  );
  assert.match(transferegovJob, /--year-from "2021"/);
  assert.doesNotMatch(
    transferegovJob,
    /collect_transferegov_historical_amendments[\s\S]*--year-from "\$\{\{/,
  );
});

test("transferências especiais usam job próprio e corredor privado", () => {
  const job = workflow.slice(workflow.indexOf("  bahia_special_transfers:"));

  assert.match(workflow, /include_bahia_special_transfers:/);
  assert.match(job, /name: Preservar transferências especiais da Bahia/);
  assert.match(
    job,
    /barreiras_collectors\.commands\.collect_bahia_special_transfers/,
  );
  assert.match(job, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(job, /SUPABASE_RAW_ARTIFACTS_BUCKET: raw-artifacts/);
  assert.match(job, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.doesNotMatch(job, /CNPJ_CPF_CREDOR_PAGAMENTO/);
});

test("transferências especiais são normalizadas no mesmo job após preservação", () => {
  const start = workflow.indexOf("  bahia_special_transfers:");
  const end = workflow.indexOf("\n  bahia_state_loa_amendments:", start);
  const job = workflow.slice(start, end);

  assert.match(
    job,
    /PYTHONPATH: workers\/collectors\/src:workers\/normalization\/src/,
  );
  assert.match(
    job,
    /barreiras_collectors\.commands\.collect_bahia_special_transfers[\s\S]+barreiras_normalization\.commands\.process_bahia_special_transfers/,
  );
  assert.match(job, /--limit "1"/);
});
