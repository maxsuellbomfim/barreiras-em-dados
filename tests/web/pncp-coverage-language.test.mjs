import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const ts = requireWeb("typescript");
const { createElement } = requireWeb("react");
const { renderToStaticMarkup } = requireWeb("react-dom/server");
const source = readFileSync(new URL("../../apps/web/app/licitacoes/procurement-explorer.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
}}).outputText;
const mod = { exports: {} };
new Function("require", "module", "exports", compiled)(requireWeb, mod, mod.exports);
const { ProcurementExplorer } = mod.exports;
const fixture = state => ({
  controlNumber: "13654405000195-1-000001/2025", ano: 2025, sequencial: 1,
  modalidade: "Pregão", objeto: "Aquisição de equipamentos", situacao: null,
  unidade: null, valorEstimado: 100, valorHomologado: null, dataPublicacao: null,
  itens: [], resultados: [], methodologyVersion: "test",
  executionSummary: { state, methodologyVersion: "test", contractsCount: 0,
    commitmentsCount: 0, liquidationsCount: 0, paymentsCount: 0,
    contractCurrentAmount: 0, committedAmount: 0, liquidatedAmount: 0, paidAmount: 0,
    contracts: [], evidenceCount: 0, evidence: [], },
});
const render = state => renderToStaticMarkup(createElement(ProcurementExplorer, { procurements: [fixture(state)] }));

for (const state of ["linked", "no_linked_execution", "not_normalized", "not_available"]) {
  test(`aviso de cobertura visível sem abrir detalhes: ${state}`, () => {
    const html = render(state);
    const note = html.indexOf('class="meta-note procurement-coverage-note"');
    assert.ok(note >= 0);
    assert.ok(note < html.indexOf('<details class="procurement-execution"'));
    assert.match(html, /não confirma que todos os contratos e pagamentos foram coletados/);
    assert.match(html, /A ausência de um vínculo aqui não prova que ele não exista na fonte oficial/);
    assert.doesNotMatch(html, /HTTP 404|HTTP 204|coleta completa|consulta concluída|vazio confirmado/);
    assert.match(html, /https:\/\/pncp.gov.br\/app\/editais\/13654405000195\/2025\/1/);
  });
}

test("ausência descreve a plataforma sem afirmar ausência na fonte", () => {
  const html = render("no_linked_execution");
  assert.match(html, /Ainda não publicamos vínculos/);
  assert.match(html, /O motivo pode ser uma coleta pendente, uma resposta inconclusiva ou a falta de um vínculo validado/);
  assert.doesNotMatch(html, /A contratação foi normalizada, mas ainda não há contrato/);
});

test("preparação e resumo indisponível têm mensagens diferentes sem jargão", () => {
  assert.match(render("not_normalized"), /Os vínculos desta contratação ainda estão em preparação/);
  assert.match(render("not_available"), /O resumo dos vínculos não está disponível neste momento/);
  assert.doesNotMatch(render("not_normalized"), /ainda não foi normalizada/);
});

test("vínculos conhecidos conservam contagens e valores no recorte", () => {
  const item = fixture("linked");
  item.executionSummary.contractsCount = 2;
  item.executionSummary.contractCurrentAmount = 1234.56;
  const html = renderToStaticMarkup(createElement(ProcurementExplorer, { procurements: [item] }));
  assert.match(html, /<dt>Contratos<\/dt><dd>2<\/dd>/);
  assert.match(html, /1\.234,56/);
  assert.match(html, /Os valores abaixo se referem somente aos registros vinculados nesta plataforma/);
});
