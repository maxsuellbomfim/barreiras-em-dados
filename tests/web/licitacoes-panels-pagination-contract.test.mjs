import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const page = read("apps/web/app/licitacoes/page.tsx");
const contracts = read("apps/web/lib/municipal-contracts.ts");
const processes = read("apps/web/lib/municipal-procurement-processes.ts");
const migration = read("supabase/migrations/20260923170727_paginate_municipal_procurement_panels.sql");

test("painéis municipais paginam no servidor em vez de enviar 100 cartões", () => {
  for (const lib of [contracts, processes]) {
    assert.match(lib, /const PAGE_SIZE = 24;/);
    assert.match(lib, /page_size: PAGE_SIZE \+ 1/);
    assert.match(lib, /page_offset: \(page - 1\) \* PAGE_SIZE/);
    assert.doesNotMatch(lib, /page_size: 100/);
  }
  assert.equal((migration.match(/limit page_size offset page_offset;/g) ?? []).length, 2);
  assert.match(page, /parsePanelPage\(params\.contratos\)/);
  assert.match(page, /parsePanelPage\(params\.processos\)/);
  // Página fora do intervalo volta à primeira, sem consulta com offset absurdo.
  assert.match(page, /page >= 1 && page <= 500 \? page : 1/);
});

test("sanções aparecem por fornecedor, com o detalhe na página própria", () => {
  assert.match(page, /sanctionsBySupplier\(result\.sanctions\)/);
  assert.match(page, /href=\{`\/licitacoes\/fornecedor\/\$\{supplier\.cnpj\}#supplier-sanctions-title`\}/);
  assert.match(page, /não afirma\s+culpa nem irregularidade em contratos específicos/);
  assert.doesNotMatch(page, /<SupplierSanctionCard/);
});
