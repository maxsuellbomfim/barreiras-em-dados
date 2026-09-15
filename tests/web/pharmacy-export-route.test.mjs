import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import test from 'node:test';
import * as csv from '../../apps/web/lib/pharmacy-csv.mjs';
import * as selection from '../../apps/web/lib/pharmacy-establishments.mjs';
const requireWeb=createRequire(new URL('../../apps/web/package.json',import.meta.url));
const ts=requireWeb('typescript');
const code=await readFile(new URL('../../apps/web/app/recursos/saude/exportar/route.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const selected='a'.repeat(64);
const record={id:selected,establishment:'FARMÁCIA TESTE',date:'2025-02-07',amount:'10.00',sha256:'b'.repeat(64)};
function route(loader){
  const module={exports:{}};
  new Function('require','module','exports',compiled)(id=>{
    if(id==='../../../../lib/pharmacy')return {getPharmacyExport:loader};
    if(id==='../../../../lib/pharmacy-csv.mjs')return csv;
    if(id==='../../../../lib/pharmacy-establishments.mjs')return selection;
    return requireWeb(id);
  },module,module.exports);
  return module.exports;
}
const request=query=>new Request(`https://example.test/recursos/saude/exportar${query}`);
test('CSV route exports exactly the requested year/filter with download and no-store headers',async()=>{
  const calls=[];
  const {GET,dynamic,revalidate}=route(async(...args)=>{calls.push(args);return {status:'ready',year:2025,establishment:selected,records:[record]};});
  const response=await GET(request(`?ano=2025&estabelecimento=${selected}`));
  assert.equal(dynamic,'force-dynamic');assert.equal(revalidate,0);
  assert.deepEqual(calls,[[2025,selected]]);assert.equal(response.status,200);
  assert.match(response.headers.get('Content-Type'),/^text\/csv; charset=utf-8$/);
  assert.equal(response.headers.get('Content-Disposition'),'attachment; filename="farmacia-popular-2025-estabelecimento.csv"');
  assert.match(response.headers.get('Cache-Control'),/no-store/);assert.equal(response.headers.get('X-Content-Type-Options'),'nosniff');
  const body=await response.text();assert.match(body,/"10,00"/);assert.match(body,/Cobertura parcial/);
});
test('repeated, invalid or unsupported query parameters fail before the public RPC',async()=>{
  const {GET}=route(()=>assert.fail('RPC must not run'));
  for(const query of ['', '?ano=2020','?ano=2025&ano=2024','?ano=2025e0','?ano=2025.0','?ano=2025&estabelecimento=',`?ano=2025&estabelecimento=${selected}&estabelecimento=${selected}`,'?ano=2025&pagina=2','?ano=2025&foo=private']){
    const response=await GET(request(query));assert.equal(response.status,400,query);
    assert.equal(response.headers.get('Content-Disposition'),null);assert.match(response.headers.get('Cache-Control'),/no-store/);
    assert.doesNotMatch(await response.text(),/foo|private|2025e0/);
  }
});
test('pending, RPC failure and exceptions never download an empty or partial CSV',async()=>{
  for(const state of ['pending','unavailable','throw']){
    const {GET}=route(async()=>{if(state==='throw')throw Error('private secret');return {status:state};});
    const response=await GET(request('?ano=2025'));
    assert.equal(response.status,state==='pending'?409:503);assert.equal(response.headers.get('Content-Disposition'),null);
    assert.doesNotMatch(response.headers.get('Content-Type'),/csv/);assert.match(response.headers.get('Cache-Control'),/no-store/);
    const body=await response.text();assert.doesNotMatch(body,/private|secret|^ano;/);assert.match(body,/não significa.*zero/);
  }
  const {GET}=route(async()=>({status:'ready',year:2025,establishment:null,records:[{...record,amount:'=1+1'}]}));
  const response=await GET(request('?ano=2025'));
  assert.equal(response.status,503);assert.equal(response.headers.get('Content-Disposition'),null);
  assert.doesNotMatch(await response.text(),/=1\+1/);
});
