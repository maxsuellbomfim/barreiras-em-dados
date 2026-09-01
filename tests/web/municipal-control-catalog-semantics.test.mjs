import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { financeResourceLabel } from "../../apps/web/lib/finance-documents.ts";

const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("catálogo municipal não é apresentado como demonstrativo anual", () => {
  assert.equal(
    financeResourceLabel("pdc-contas-anuais"),
    "Legislação de controle e prestação de contas",
  );
  assert.match(page, /não contém os demonstrativos anuais/i);
  assert.match(page, /DCA do Tesouro/i);
});
