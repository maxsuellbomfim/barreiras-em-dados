import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("CSS global tem chaves balanceadas (bloco aberto aninha tudo o que vem depois)", async () => {
  const css = (await readFile(new URL("../../apps/web/app/globals.css", import.meta.url), "utf8"))
    .replace(/\/\*[\s\S]*?\*\//g, "");
  let depth = 0;
  for (const char of css) {
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    assert.ok(depth >= 0, "fechamento sem abertura");
  }
  assert.equal(depth, 0);
});
