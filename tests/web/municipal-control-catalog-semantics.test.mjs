import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import * as financeDocuments from "../../apps/web/lib/finance-documents.ts";

const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("catálogo municipal não é apresentado como demonstrativo anual", () => {
  assert.equal(
    financeDocuments.financeResourceLabel("pdc-contas-anuais"),
    "Legislação de controle e prestação de contas",
  );
  assert.match(page, /não contém os demonstrativos anuais/i);
  assert.match(page, /DCA do Tesouro/i);
});

test("a página combina famílias sem perder documentos fora do limite geral", () => {
  assert.equal(
    typeof financeDocuments.mergePublicFinanceDocumentResults,
    "function",
  );
  const operational = { documentId: "operational" };
  const control = { documentId: "control" };
  const fiscal = { documentId: "fiscal" };
  const merged = financeDocuments.mergePublicFinanceDocumentResults(
    { state: "available", documents: [operational, fiscal] },
    { state: "available", documents: [control] },
    { state: "available", documents: [fiscal] },
    { state: "unavailable" },
  );

  assert.deepEqual(
    merged.map(({ documentId }) => documentId),
    ["operational", "fiscal", "control"],
  );
  assert.match(page, /getPublicFinanceDocuments\("pdc-contas-anuais"\)/);
  assert.match(page, /getPublicFinanceDocuments\("balancetes"\)/);
});
