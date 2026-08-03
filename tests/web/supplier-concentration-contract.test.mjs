import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260806180000_public_supplier_concentration.sql",
    import.meta.url,
  ),
  "utf8",
);
const conservativeMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260806181000_conservative_supplier_signal.sql",
    import.meta.url,
  ),
  "utf8",
);
const monitoringMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260806182000_supplier_monitoring_context.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(
  new URL("../../apps/web/lib/supplier-concentration.ts", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url),
  "utf8",
);

test("resumo de fornecedores usa resultados PNCP deduplicados e valor homologado", () => {
  assert.match(migration, /get_public_supplier_concentration/);
  assert.match(migration, /pncp_resultado/);
  assert.match(migration, /numeroControlePNCPCompra/);
  assert.match(migration, /valorTotalHomologado/);
  assert.match(migration, /pncp-supplier-concentration\/1\.0\.0/);
  assert.match(migration, /não prova de irregularidade/);
});

test("sinal de concentração exige recorrência entre processos", () => {
  assert.match(conservativeMigration, /procurement_count >= 3/);
  assert.match(conservativeMigration, /procurement_count >= 2/);
  assert.match(conservativeMigration, /não prova de irregularidade/);
});

test("cliente de fornecedores valida metodologia e não expõe CPF por contrato", () => {
  assert.match(client, /pncp-supplier-concentration\/1\.0\.0/);
  assert.match(client, /PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY/);
  assert.match(client, /sourceUrl\?\.startsWith\("https:\/\/"\)/);
});

test("concentração isolada permanece visível para acompanhamento histórico", () => {
  assert.match(monitoringMigration, /procurement_count = 1/);
  assert.match(monitoringMigration, /Mantemos o registro visível/);
  assert.match(monitoringMigration, /ausência de recorrência impede/);
  assert.match(page, /acompanhar histórico/);
});
