import assert from "node:assert/strict";
import test from "node:test";

const filterModule = await import(
  "../../apps/web/lib/state-loa-year-filter.mjs"
).catch(() => ({
  resolveStateLoaYear: () => null,
  stateLoaYears: () => [],
}));

const { resolveStateLoaYear, stateLoaYears } = filterModule;

test("seleciona por padrão o ano estadual mais recente", () => {
  assert.equal(resolveStateLoaYear(undefined, 2026), 2026);
  assert.equal(resolveStateLoaYear([], 2026), 2026);
  assert.deepEqual(stateLoaYears(2026), [2026, 2025, 2024, 2023, 2022]);
});

test("aceita somente um ano coberto da LOA estadual", () => {
  assert.equal(resolveStateLoaYear("2024", 2026), 2024);
  assert.equal(resolveStateLoaYear(["2023"], 2026), 2023);
  assert.equal(resolveStateLoaYear(["2023", "2024"], 2026), 2026);
  assert.equal(resolveStateLoaYear("2021", 2026), 2026);
  assert.equal(resolveStateLoaYear("9999", 2026), 2026);
  assert.equal(resolveStateLoaYear("2024abc", 2026), 2026);
});
