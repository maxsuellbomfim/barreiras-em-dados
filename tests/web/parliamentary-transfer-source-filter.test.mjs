import assert from "node:assert/strict";
import test from "node:test";

const sourceModule = await import(
  "../../apps/web/lib/parliamentary-transfer-source-filter.mjs"
).catch(() => ({}));

const resolveTransferSourceSelection =
  sourceModule.resolveTransferSourceSelection ?? (() => ({
    source: "federal-atual",
    showCurrentFederal: true,
    showHistoricalFederal: true,
    showState: true,
  }));

test("sem origem solicitada abre somente a API federal atual", () => {
  assert.deepEqual(resolveTransferSourceSelection(undefined), {
    source: "federal-atual",
    showCurrentFederal: true,
    showHistoricalFederal: false,
    showState: false,
  });
});

test("arquivo federal histórico não exibe a API atual nem a fonte estadual", () => {
  assert.deepEqual(resolveTransferSourceSelection("federal-historico"), {
    source: "federal-historico",
    showCurrentFederal: false,
    showHistoricalFederal: true,
    showState: false,
  });
});

test("fonte estadual aparece isolada das duas séries federais", () => {
  assert.deepEqual(resolveTransferSourceSelection("estadual"), {
    source: "estadual",
    showCurrentFederal: false,
    showHistoricalFederal: false,
    showState: true,
  });
});

test("origem inválida ou repetida volta com segurança para federal atual", () => {
  assert.equal(resolveTransferSourceSelection("todas").source, "federal-atual");
  assert.equal(
    resolveTransferSourceSelection(["estadual", "federal-historico"]).source,
    "federal-atual",
  );
});
