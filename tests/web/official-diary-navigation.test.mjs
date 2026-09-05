import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import * as index from "../../apps/web/lib/integral-gazette-index.mjs";

test("navegação promete Diário Oficial literal, não tradução ou resumo", async () => {
  for (const path of ["page.tsx", "atos/page.tsx", "licitacoes/page.tsx", "representantes/page.tsx"]) {
    const content = await readFile(new URL(`../../apps/web/app/${path}`, import.meta.url), "utf8");
    assert.doesNotMatch(content, /Diário traduzido/i, path);
    assert.match(content, /Diário Oficial/, path);
  }
  const home = await readFile(new URL("../../apps/web/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /Texto integral, organizado por documento, com acesso à fonte oficial\./);
});

test("Diário distingue indisponibilidade, busca vazia, fim da paginação e catálogo sem texto", () => {
  assert.equal(typeof index.getIntegralGazetteListState, "function");
  const base = { state: "available", editionCount: 0, catalogCount: 20, query: "", pageNumber: 1 };
  for (const [input, expected] of [
    [{ ...base, state: "unavailable" }, "unavailable"],
    [{ ...base, editionCount: 1 }, "available"],
    [{ ...base, query: "termo sem ocorrência" }, "search_empty"],
    [{ ...base, pageNumber: 99 }, "page_empty"],
    [base, "catalog_only"],
    [{ ...base, catalogCount: 0 }, "empty"],
    [{ ...base, catalogCount: null }, "empty"],
  ]) assert.equal(index.getIntegralGazetteListState(input), expected);
});
