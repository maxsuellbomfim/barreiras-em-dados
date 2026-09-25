import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../../apps/web/app/page.tsx", import.meta.url), "utf8");

test("página inicial mantém os quatro cartões mesmo com falha de consulta", () => {
  for (const card of ["annualCard", "monthlyCard", "payrollCard", "diaryCard"]) {
    assert.match(home, new RegExp(String.raw`${card}\(\w+\) \?\?\s*unavailable\(`), card);
  }
  assert.match(home, /não ausência de dados/);
  assert.doesNotMatch(home, /R\$ 0/);
});
