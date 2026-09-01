import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

function rule(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `regra CSS ausente: ${selector}`);
  return match[1];
}

test("estudo territorial permite que a trilha principal encolha no celular", async () => {
  const css = await readFile(new URL("../globals.css", import.meta.url), "utf8");

  assert.match(
    rule(css, ".territorial-study"),
    /grid-template-columns\s*:\s*minmax\(0\s*,\s*1fr\)/,
  );
  assert.match(rule(css, ".territorial-study > *"), /min-width\s*:\s*0/);
  assert.match(rule(css, ".territorial-filters label"), /min-width\s*:\s*0/);
  assert.match(
    rule(css, ".territorial-filters select,\n.territorial-filters input"),
    /max-width\s*:\s*100%/,
  );
});

test("tabela territorial mantém rolagem local em vez de alargar a página", async () => {
  const css = await readFile(new URL("../globals.css", import.meta.url), "utf8");

  const tableWrap = rule(css, ".territorial-table-wrap");
  assert.match(tableWrap, /max-width\s*:\s*100%/);
  assert.match(tableWrap, /overflow-x\s*:\s*auto/);
  assert.match(tableWrap, /overscroll-behavior-inline\s*:\s*contain/);
});
