import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import test from 'node:test';
import * as selectionHelpers from '../../apps/web/lib/pharmacy-establishments.mjs';
const requireWeb=createRequire(new URL('../../apps/web/package.json',import.meta.url));
const ts=requireWeb('typescript');
const {createElement}=requireWeb('react');
const {renderToStaticMarkup}=requireWeb('react-dom/server');
const source=await readFile(new URL('../../apps/web/app/recursos/saude/pharmacy-establishments.tsx',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}});
const module={exports:{}};
new Function('require','module','exports',outputText)(id=>id==='../../../lib/pharmacy-establishments.mjs'?selectionHelpers:requireWeb(id),module,module.exports);
const {PharmacyEstablishments}=module.exports;
const a='a'.repeat(64),b='b'.repeat(64),c='c'.repeat(64);
const defaults={year:2025,page:4,optionsPage:2,selection:a,selectedName:'Selecionada fora desta página',
  options:{status:'ready',hasNext:true,records:[{establishment_id:b,establishment:'Nome igual'},{establishment_id:c,establishment:'Nome igual'}]}};
const render=props=>renderToStaticMarkup(createElement(PharmacyEstablishments,{...defaults,...props}));
test('filter options preserve homonyms and keep selected context outside the options page',()=>{
  const html=render({});
  assert.match(html,/Selecionada fora desta página/);
  for(const id of [b,c]) assert.match(html,new RegExp(`href="\\?ano=2025&amp;estabelecimento=${id}"`));
  assert.equal((html.match(/>Nome igual<\/a>/g)||[]).length,2);
  assert.match(html,/Referência documental/);
  assert.match(html,new RegExp(`ano=2025&amp;estabelecimento=${a}&amp;pagina=4&amp;opcoes=3`));
  assert.match(html,/href="\?ano=2025"[^>]*>Ver todos os estabelecimentos/);
  assert.doesNotMatch(html,/scope_key|CNPJ|CPF/);
});
test('invalid selection is not rendered or silently removed; recovery is explicit',()=>{
  const html=render({selection:'PRIVATE_INVALID_VALUE',selectedName:undefined});
  assert.match(html,/Não foi possível validar o estabelecimento selecionado/);
  assert.match(html,/Ver todos os estabelecimentos/);
  assert.doesNotMatch(html,/PRIVATE_INVALID_VALUE|Páginas dos estabelecimentos/);
});
test('unavailable or empty options do not claim that pharmacies or payments do not exist',()=>{
  const failed=render({selection:null,options:{status:'unavailable',records:[],hasNext:false}});
  assert.match(failed,/opções de estabelecimento estão temporariamente indisponíveis/);
  const empty=render({selection:null,options:{status:'ready',records:[],hasNext:false}});
  assert.match(empty,/Nenhuma opção nesta página/);
  assert.match(empty,/não comprova ausência de pagamentos/);
});
