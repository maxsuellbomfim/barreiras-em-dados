import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import * as procurementTitle from "../../apps/web/lib/procurement-title.mjs";

const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const ts = requireWeb("typescript");
const { createElement } = requireWeb("react");
const { renderToStaticMarkup } = requireWeb("react-dom/server");
const source = readFileSync(new URL("../../apps/web/app/licitacoes/procurement-explorer.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
}}).outputText;
const mod = { exports: {} };
const urlSource = readFileSync(new URL("../../apps/web/lib/pncp-source-url.ts", import.meta.url), "utf8");
const urlMod = { exports: {} };
new Function("module", "exports", ts.transpileModule(urlSource, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}}).outputText)(urlMod, urlMod.exports);
new Function("require", "module", "exports", compiled)(
  id => id === "../../lib/pncp-source-url" ? urlMod.exports
    : id === "../../lib/procurement-title.mjs" ? procurementTitle
    : requireWeb(id),
  mod, mod.exports,
);
const { ProcurementExplorer, ProcurementCard } = mod.exports;
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
// O cartão completo (página da contratação) concentra a linguagem de cobertura.
const renderCard = procurement => renderToStaticMarkup(createElement(ProcurementCard, { procurement }));
const render = state => renderCard(fixture(state));

test("aguardando publicação informa a fonte e não afirma inexistência",()=>{
 const html=renderCard({
  ...fixture("no_linked_execution"),queryStatus:{state:"awaiting_source_publication",checkedAt:"2026-09-21T19:00:00Z",sourceUrl:null}
 });
 assert.match(html,/Aguardando publicação de contrato no PNCP/);
 assert.match(html,/não prova que o contrato não exista em outras fontes/);
 assert.doesNotMatch(html,/raw_artifact|sha256/);
});

test("card do Fundo abre seu registro oficial, sem trocar o CNPJ pelo da Prefeitura", () => {
  const procurement = { ...fixture("not_available"), controlNumber: "13250888000162-1-000003/2026", ano: 2025, sequencial: 99 };
  const html = renderToStaticMarkup(createElement(ProcurementExplorer, { procurements: [procurement] }));
  assert.match(html, /href="https:\/\/pncp.gov.br\/app\/editais\/13250888000162\/2026\/3"/);
  assert.doesNotMatch(html, /app\/editais\/13654405000195/);
});

test("card com identificador inválido mantém o registro sem inventar URL", () => {
  const procurement = { ...fixture("not_available"), controlNumber: "invalid" };
  const html = renderToStaticMarkup(createElement(ProcurementExplorer, { procurements: [procurement] }));
  assert.match(html, /Link oficial indisponível: identificador não validado/);
  assert.doesNotMatch(html, /app\/editais\//);
});

test("estado individual aparece antes dos detalhes com data e escopo restrito", () => {
  const procurement = {...fixture("linked"), queryStatus: {state:"query_complete",checkedAt:"2026-09-15T20:00:00Z",sourceUrl:"https://pncp.gov.br/app/editais/13654405000195/2025/1"}};
  const html = renderCard(procurement);
  assert.match(html,/Consulta de contratos concluída/);
  assert.match(html,/<time dateTime="2026-09-15T20:00:00Z">/);
  assert.ok(html.indexOf('class="procurement-query-status"')<html.indexOf('<details class="procurement-execution">'));
  assert.match(html,/não comprova pagamentos nem execução/);
});
test("cada limitação individual tem mensagem própria sem falso zero", () => {
  const states={unknown:"Verificação individual ainda não disponível",pending:"Consulta pendente de conclusão",inconclusive:"Resposta do PNCP inconclusiva",partial:"Consulta com páginas pendentes",interrupted:"Consulta interrompida",empty_confirmed:"Resposta vazia confirmada nesta consulta",unavailable:"Estado da consulta temporariamente indisponível"};
  for(const [state,label] of Object.entries(states)) {
    const html=renderCard({...fixture("no_linked_execution"),queryStatus:{state,checkedAt:null,sourceUrl:null}});
    assert.ok(html.includes(label),state);
    assert.doesNotMatch(html,/não existem contratos|nenhum pagamento foi feito|R\$\s*0,00/);
  }
});

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
  const html = renderCard(item);
  assert.match(html, /<dt>Contratos<\/dt><dd>2<\/dd>/);
  assert.match(html, /1\.234,56/);
  assert.match(html, /Os valores abaixo se referem somente aos registros vinculados nesta plataforma/);
});

test("a lista mostra cartões compactos que levam à página própria", () => {
  const item = { ...fixture("linked"), itens: [{ numeroItem: 1, descricao: "Cadeira", quantidade: 2, unidade: "UN", valorUnitarioEstimado: 10, valorTotal: 20, situacao: null, contextoPreco: null }] };
  const html = renderToStaticMarkup(createElement(ProcurementExplorer, { procurements: [item] }));
  assert.match(html, /href="\/licitacoes\/contratacao\/13654405000195-1-000001%2F2025"/);
  assert.match(html, /1 item\(ns\)/);
  assert.doesNotMatch(html, /Cadeira/, "itens ficam fora da listagem");
  assert.doesNotMatch(html, /<details class="procurement-execution"/);
  // O aviso de cobertura continua visível sem abrir nada, uma vez para a lista.
  assert.match(html, /não confirma que todos os contratos e pagamentos foram coletados/);
  assert.match(html, /A ausência de um vínculo aqui não prova que ele não exista na fonte oficial/);
});
