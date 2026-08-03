import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const revenuePublisher = await readFile(
  new URL(
    "../../workers/normalization/src/barreiras_normalization/revenue_publisher.py",
    import.meta.url,
  ),
  "utf8",
);
const expensePublisher = await readFile(
  new URL(
    "../../workers/normalization/src/barreiras_normalization/expense_publisher.py",
    import.meta.url,
  ),
  "utf8",
);

test("publicadores financeiros selecionam cada PDF uma única vez", () => {
  assert.match(revenuePublisher, /select distinct on \(document\.id\)/);
  assert.match(expensePublisher, /select distinct on \(document\.id\)/);
  assert.match(revenuePublisher, /order by document\.id, record\.created_at desc/);
  assert.match(expensePublisher, /order by document\.id, record\.created_at desc/);
});
