import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import test from "node:test";
const requireWeb=createRequire(new URL("../../apps/web/package.json",import.meta.url));
const ts=requireWeb("typescript");
let source=""; try {source=readFileSync(new URL("../../apps/web/lib/pncp-query-status.ts",import.meta.url),"utf8");} catch(e){if(e.code!=="ENOENT")throw e;}
const mod={exports:{fetchPncpQueryStatuses:async()=>new Map()}};
if(source)new Function("require","module","exports",ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(requireWeb,mod,mod.exports);
const {fetchPncpQueryStatuses}=mod.exports;
const key="13654405000195-1-000027/2026";
const row={control_number:key,state:"query_complete",checked_at:"2026-09-15T20:00:00Z",source_url:"https://pncp.gov.br/app/editais/13654405000195/2026/27"};
test("compra de fundo municipal não apaga estados das compras da Prefeitura",async()=>{
  const fund="13250888000162-1-000003/2026";
  const calls=[];
  const result=await fetchPncpQueryStatuses("https://example.supabase.co","sb_publishable_test",[fund,key,key],async(url,init)=>{
    calls.push(JSON.parse(init.body));
    return {ok:true,json:async()=>[row]};
  });
  assert.equal(result.get(key)?.state,"query_complete");
  assert.equal(result.has(fund),false);
  assert.deepEqual(calls,[{control_numbers:[key]}]);
});
test("lote sem controles atendidos não consulta nem inventa cobertura",async()=>{
  let called=false;
  const result=await fetchPncpQueryStatuses("https://example.supabase.co","test",["13250888000162-1-000003/2026"],async()=>{called=true;throw Error("unexpected");});
  assert.equal(called,false);
  assert.equal(result.size,0);
});
test("limite do lote e controle malformado não são contornados pelo filtro",async()=>{
  let calls=0;
  const fetcher=async()=>{calls++;return {ok:true,json:async()=>[row]};};
  const tooMany=Array.from({length:61},(_,index)=>`13654405000195-1-${index+1}/2026`);
  assert.equal((await fetchPncpQueryStatuses("https://example.supabase.co","test",tooMany,fetcher)).size,0);
  assert.equal((await fetchPncpQueryStatuses("https://example.supabase.co","test",[key+"\n"],fetcher)).size,0);
  assert.equal(calls,0);
});
test("cliente recebe somente metadados do lote solicitado",async()=>{
  const calls=[];
  const result=await fetchPncpQueryStatuses("https://example.supabase.co","sb_publishable_test",[key],async(url,init)=>{calls.push({url,init});return {ok:true,json:async()=>[row]};});
  assert.equal(result.get(key)?.state,"query_complete");
  assert.deepEqual(JSON.parse(calls[0].init.body),{control_numbers:[key]});
  assert.match(calls[0].url,/get_pncp_contract_query_status$/);
});
test("resposta incompleta, duplicada, estrangeira ou inválida não fabrica estado",async()=>{
  for(const payload of [[],[row,row],[{...row,control_number:"other"}],[{...row,checked_at:"invalid"}],[{...row,state:"complete_history"}],[{...row,source_url:"https://attacker.invalid/"}],{}]) {
    const result=await fetchPncpQueryStatuses("https://example.supabase.co","sb_publishable_test",[key],async()=>({ok:true,json:async()=>payload}));
    assert.equal(result.size,0);
  }
});
test("falha de consulta não impede os contratos existentes de serem exibidos",async()=>{
  for(const fetcher of [async()=>({ok:false}),async()=>{throw Error("network");}]) {
    const result=await fetchPncpQueryStatuses("https://example.supabase.co","sb_publishable_test",[key],fetcher);
    assert.equal(result.size,0);
  }
});
