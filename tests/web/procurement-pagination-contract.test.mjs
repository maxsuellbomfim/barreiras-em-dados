import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../../apps/web/${path}`, import.meta.url), "utf8");

test("Compras pagina no banco, 20 por página, preservando os filtros", async () => {
  const [lib, page] = await Promise.all([read("lib/pncp-procurements.ts"), read("app/licitacoes/page.tsx")]);
  assert.match(lib, /get_pncp_procurements_page/);
  assert.match(lib, /page_offset: offset/);
  assert.match(page, /const PROCUREMENTS_PER_PAGE = 20;/);
  assert.match(page, /PROCUREMENTS_PER_PAGE \+ 1,\s*\(procurementPage - 1\) \* PROCUREMENTS_PER_PAGE/);
  assert.match(page, /param="pagina"/);
});
