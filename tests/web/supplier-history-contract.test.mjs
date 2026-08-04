import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260803133120_public_supplier_history.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(
  new URL("../../apps/web/lib/supplier-history.ts", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/licitacoes/fornecedor/[supplierKey]/page.tsx", import.meta.url),
  "utf8",
);

test("histórico de fornecedor deduplica processos e preserva valores do PNCP", () => {
  assert.match(migration, /get_public_supplier_history/);
  assert.match(migration, /numeroControlePNCPCompra/);
  assert.match(migration, /group by rows\.supplier_key, rows\.control_number/);
  assert.match(migration, /pncp-supplier-history\/1\.0\.0/);
});

test("cliente e página de histórico exigem fonte e metodologia", () => {
  assert.match(client, /pncp-supplier-history\/1\.0\.0/);
  assert.match(client, /PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY/);
  assert.match(page, /Ver registro oficial do PNCP/);
  assert.match(page, /não é avaliação de legalidade/);
});
