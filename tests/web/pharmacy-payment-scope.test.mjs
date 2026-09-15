import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import test from 'node:test';

// Use the app's existing compiler/runtime to test the actual server component.
// No browser bundle, extra dependency, network or real financial data is needed.
const requireWeb = createRequire(new URL('../../apps/web/package.json', import.meta.url));
const ts = requireWeb('typescript');
const { createElement } = requireWeb('react');
const { renderToStaticMarkup } = requireWeb('react-dom/server');
async function compile(relative, dependencies = {}) {
  const source = await readFile(new URL(relative, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022 },
    fileName: relative,
  });
  const module = { exports: {} };
  new Function('require', 'module', 'exports', outputText)(
    id => Object.hasOwn(dependencies, id) ? dependencies[id] : requireWeb(id),
    module, module.exports,
  );
  return module.exports;
}
const revenues = await compile('../../apps/web/lib/revenues.ts');
const { PharmacyPayments } = await compile(
  '../../apps/web/app/recursos/saude/pharmacy-payments.tsx',
  { '../../../lib/revenues': revenues },
);
const record = { id: 'test-1', establishment: 'Farmácia de teste', date: '2025-02-07',
  amount: '10.00', sha256: 'a'.repeat(64) };
const render = props => renderToStaticMarkup(createElement(PharmacyPayments, props));
const guide = html => html.match(/<aside[^>]*aria-labelledby="pharmacy-scope-title"[^>]*>([\s\S]*?)<\/aside>/)?.[1];

test('scope warning is visible in every publication and coverage state', () => {
  for (const status of ['ready', 'pending', 'unavailable', 'empty_page']) {
    for (const coverageStatus of [undefined, 'partial', 'pending', 'unavailable']) {
      const html = render({ publication: { status, year: 2025, records: status === 'ready' ? [record] : [] },
        coverage: coverageStatus && { status: coverageStatus, year: 2025,
          published_documents: 1, establishments: 1, first_date: '2025-02-07', last_date: '2025-02-07' } });
      const content = guide(html);
      assert.ok(content, `${status}/${coverageStatus}: missing visible scope guide`);
      assert.match(content, /<h2 id="pharmacy-scope-title">Por que uma farmácia pode não aparecer\?/);
      assert.match(content, /lista é parcial/);
      assert.match(content, /matriz/);
      assert.match(content, /filial/);
      assert.match(content, /total da rede não é atribuído a Barreiras/);
      assert.match(content, /não comprova que ela deixou de receber/);
      assert.doesNotMatch(content, /<details|hidden|aria-hidden/);
      if (status === 'ready') assert.ok(html.indexOf(content) < html.indexOf('Registros de 2025'));
    }
  }
});

test('empty page offers a same-year way back without claiming zero or pending publication', () => {
  for (const year of [2021,2025,2026]) {
    const html=render({publication:{status:'empty_page',year,records:[]}});
    assert.match(html,/<aside class="transfer-reading-guide pharmacy-page-status"/);
    assert.match(html,/Nenhum pagamento nesta página/);
    assert.match(html,new RegExp(`href="\\?ano=${year}"[^>]*>Voltar à primeira página`));
    assert.doesNotMatch(html,/Publicação dos pagamentos em preparação|Dados temporariamente indisponíveis|Ainda não há registros liberados nesta página/);
    assert.match(html,/não comprova ausência de pagamentos/);
    assert.doesNotMatch(html,/<li[^>]*class="transfer-reading-guide"/);
  }
});

test('empty-page recovery keeps readable text and an identifiable link',async()=>{
  const css=await readFile(new URL('../../apps/web/app/globals.css',import.meta.url),'utf8');
  assert.match(css,/\.pharmacy-page-status p\s*\{[^}]*font-size:\s*1rem/);
  assert.match(css,/\.pharmacy-page-status a\s*\{[^}]*text-decoration:\s*underline/);
});

test('guide does not expose identities or alter published amounts and pagination', () => {
  const html = render({ publication: { status: 'ready', year: 2025, records: [record],
    privateMatrix: 'PRIVATE_MATRIX', privateIdentifier: 'PRIVATE_IDENTIFIER' },
    filters: createElement('form', { 'aria-label': 'Filtrar pagamentos por ano' }),
    navigation: createElement('a', { href: '?ano=2025&pagina=2' }, 'Próxima página') });
  assert.equal((html.match(/Farmácia de teste/g) ?? []).length, 1);
  assert.match(html, /10,00/);
  assert.match(html, /Próxima página/);
  assert.match(html, /Filtrar pagamentos por ano/);
  assert.doesNotMatch(html, /PRIVATE_MATRIX|PRIVATE_IDENTIFIER/);
  assert.doesNotMatch(guide(html) ?? '', /592|310|CNPJ|335/);
});
