import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildParliamentaryTransferQueryPlan,
} from "../../apps/web/lib/parliamentary-transfer-query-plan.mjs";

const client = readFileSync(
  new URL("../../apps/web/lib/parliamentary-transfers.ts", import.meta.url),
  "utf8",
);
const resourcesPage = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

test("cada aba consulta somente a família de recursos que exibe", () => {
  assert.deepEqual(buildParliamentaryTransferQueryPlan("current"), {
    current: true,
    historical: false,
    state: false,
  });
  assert.deepEqual(buildParliamentaryTransferQueryPlan("historical"), {
    current: false,
    historical: true,
    state: false,
  });
  assert.deepEqual(buildParliamentaryTransferQueryPlan("state"), {
    current: false,
    historical: false,
    state: true,
  });
  assert.deepEqual(buildParliamentaryTransferQueryPlan("none"), {
    current: false,
    historical: false,
    state: false,
  });
});

test("escopo desconhecido falha fechado sem consultar todas as fontes", () => {
  assert.deepEqual(buildParliamentaryTransferQueryPlan("all"), {
    current: false,
    historical: false,
    state: false,
  });
  assert.deepEqual(buildParliamentaryTransferQueryPlan(undefined), {
    current: false,
    historical: false,
    state: false,
  });
});

test("a página encaminha o escopo e o cliente condiciona cada família de RPC", () => {
  assert.match(resourcesPage, /queryScope:\s*parliamentaryTransferQueryScope/);
  assert.match(
    client,
    /plan\.current\s*\?\s*callRpc\("get_public_parliamentary_transfer_coverage"/,
  );
  assert.match(
    client,
    /plan\.historical\s*\?\s*callRpc\("get_public_federal_transfer_proposals"/,
  );
  assert.match(
    client,
    /plan\.state\s*\?\s*callRpc\("get_public_bahia_state_loa_amendments"/,
  );
  assert.match(client, /fetchPublicRpcRows/);
});
