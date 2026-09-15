import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import test from 'node:test';
import * as csv from '../../apps/web/lib/pharmacy-csv.mjs';
import * as selection from '../../apps/web/lib/pharmacy-establishments.mjs';
const requireWeb=createRequire(new URL('../../apps/web/package.json',import.meta.url));
const ts=requireWeb('typescript'),{createElement}=requireWeb('react'),{renderToStaticMarkup}=requireWeb('react-dom/server');
const source=await readFile(new URL('../../apps/web/app/recursos/saude/pharmacy-export.tsx',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
const module={exports:{}};
new Function('require','module','exports',compiled)(id=>id==='../../../lib/pharmacy-csv.mjs'?csv:id==='../../../lib/pharmacy-establishments.mjs'?selection:requireWeb(id),module,module.exports);
const {PharmacyExportLink}=module.exports;
const render=props=>renderToStaticMarkup(createElement(PharmacyExportLink,props));
const coverage={status:'partial',year:2025,published_documents:108,establishments:6,first_date:'2025-01-01',last_date:'2025-12-01'};
test('download link states complete selection, not this page, and retains only chosen scope',()=>{
  const all=render({year:2025,selection:null,coverage});
  assert.match(all,/href="\/recursos\/saude\/exportar\?ano=2025"/);
  assert.match(all,/Baixar consulta em CSV/);assert.match(all,/todas as páginas/);assert.match(all,/cobertura parcial/);
  const selected='a'.repeat(64);
  const filtered=render({year:2025,selection:selected,coverage:{...coverage,establishments:1,filter_applied:true,selected_establishment:'TESTE'}});
  assert.match(filtered,new RegExp(`estabelecimento=${selected}`));assert.doesNotMatch(filtered,/pagina=|opcoes=/);
});
test('download is not offered for pending, invalid or mismatched selections',()=>{
  for(const props of [{year:2020,selection:null,coverage},{year:2025,selection:'invalid',coverage},{year:2024,selection:null,coverage},{year:2025,selection:null,coverage:{status:'unavailable'}},{year:2025,selection:null,coverage:{...coverage,status:'pending',published_documents:0}}]){
    assert.doesNotMatch(render(props),/href=|download=/);
  }
  assert.match(render({year:2025,selection:null,coverage:{...coverage,published_documents:5001}}),/5.000/);
});
