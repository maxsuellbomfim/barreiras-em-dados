import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-pncp-registry.yml", import.meta.url),
  "utf8",
);

test("workflow PNCP preserva contratos/empenhos depois de itens e resultados", () => {
  assert.match(workflow, /collect_pncp_itens/);
  assert.match(workflow, /collect_pncp_contratos/);
  assert.match(workflow, /normalize_pncp_contracts/);
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /SUPABASE_RAW_ARTIFACTS_BUCKET: raw-artifacts/);
});

test("workflow manual oferece execucao apenas de contratos", () => {
  assert.match(workflow, /contracts_only/);
  assert.match(workflow, /inputs\.mode != 'contracts_only'/);
});

test("workflow manual permite replay explícito de uma janela falha", () => {
  assert.match(workflow, /replay_window/);
  assert.match(workflow, /replay_since/);
  assert.match(workflow, /replay_until/);
  assert.match(workflow, /PNCP_REPLAY_SINCE/);
  assert.match(workflow, /PNCP_REPLAY_UNTIL/);
  assert.match(workflow, /--since "\$PNCP_REPLAY_SINCE"/);
  assert.match(workflow, /--until "\$PNCP_REPLAY_UNTIL"/);
});
