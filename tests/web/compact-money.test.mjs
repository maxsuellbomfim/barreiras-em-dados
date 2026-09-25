import assert from "node:assert/strict";
import test from "node:test";

import { formatBrlCompact } from "../../apps/web/lib/compact-money.mjs";

test("valores grandes viram leitura curta em português", () => {
  assert.equal(formatBrlCompact("1052287013.35"), "R$ 1,05 bilhão");
  assert.equal(formatBrlCompact("2500000000.00"), "R$ 2,5 bilhões");
  assert.equal(formatBrlCompact("76245577.25"), "R$ 76,2 milhões");
  assert.equal(formatBrlCompact("1200000.00"), "R$ 1,2 milhão");
  assert.equal(formatBrlCompact("350000.00"), "R$ 350 mil");
  assert.equal(formatBrlCompact("812.5"), "R$ 812,50");
  assert.equal(formatBrlCompact("-47598685.94"), "-R$ 47,6 milhões");
  assert.equal(formatBrlCompact("não é número"), null);
});
