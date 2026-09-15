import assert from 'node:assert/strict';
import test from 'node:test';
import {loadPharmacyExport,serializePharmacyCsv,pharmacyExportHref} from '../../apps/web/lib/pharmacy-csv.mjs';
const row=i=>({id:i.toString(16).padStart(64,'0'),establishment:'FARMÁCIA TESTE',date:'2025-02-07',amount:'999999999999.99',sha256:'b'.repeat(64),register_sha256:'c'.repeat(64),reviewed_at:'2026-09-15T12:00:00Z',historical_registration_verified:false});
const envelope=(records,extra={})=>[{year:2025,filter_applied:false,selected_establishment:null,published_documents:records.length,establishments:records.length?1:0,status:records.length?'partial':'pending',records,...extra}];

test('export consumes exactly one envelope, not independently paginated RPC reads',async()=>{
  const calls=[],records=Array.from({length:108},(_,i)=>({...row(i),private_note:'NEVER_EXPORT'}));
  const result=await loadPharmacyExport(2025,async args=>{calls.push(args);return envelope(records);});
  assert.equal(result.status,'ready');assert.equal(result.records.length,108);
  assert.deepEqual(calls,[{p_year:2025}]);
  assert.doesNotMatch(JSON.stringify(result),/private_note|NEVER_EXPORT|register_sha256|reviewed_at/);
  assert.deepEqual(Object.keys(result.records[0]).sort(),['amount','date','establishment','id','sha256']);
});
test('export retains the selected public reference and verifies it is in the returned snapshot',async()=>{
  const selected=row(2).id,calls=[];
  const result=await loadPharmacyExport(2025,async args=>{calls.push(args);return envelope([row(1),row(2)],{filter_applied:true,selected_establishment:'FARMÁCIA TESTE'});},selected);
  assert.equal(result.status,'ready');assert.equal(result.establishment,selected);
  assert.deepEqual(calls,[{p_year:2025,p_establishment_id:selected}]);
  for(const extra of [{filter_applied:false},{establishments:2},{selected_establishment:null},{selected_establishment:'Outro nome'}]){
    assert.equal((await loadPharmacyExport(2025,async()=>envelope([row(1),row(2)],{filter_applied:true,selected_establishment:'FARMÁCIA TESTE',...extra}),selected)).status,'unavailable');
  }
  assert.equal((await loadPharmacyExport(2025,async()=>envelope([row(1)],{filter_applied:true,selected_establishment:'FARMÁCIA TESTE'}),selected)).status,'unavailable');
});
test('missing, duplicate, unordered and contradictory snapshots cannot produce an export',async()=>{
  const duplicate=Array.from({length:26},(_,i)=>row(i));duplicate[25]=row(0);
  for(const payload of [null,[],[...envelope([row(1)]),...envelope([row(2)])],envelope([row(1)],{published_documents:2}),envelope([row(1)],{year:2024}),envelope([row(1)],{establishments:0}),envelope([row(1)],{status:'complete'}),envelope([row(1)],{filter_applied:true}),envelope(duplicate),envelope([row(2),row(1)]),envelope([{...row(1),register_sha256:null}]),envelope([{...row(1),date:'2025-02-30'}])]){
    assert.equal((await loadPharmacyExport(2025,async()=>payload)).status,'unavailable');
  }
});
test('empty is pending, never zero CSV; failure is sanitized and no fallback is attempted',async()=>{
  assert.deepEqual(await loadPharmacyExport(2025,async()=>envelope([])),{status:'pending'});
  assert.equal((await loadPharmacyExport(2025,async()=>envelope([]),row(1).id)).status,'unavailable');
  assert.deepEqual(await loadPharmacyExport(2025,async()=>{throw Error('private credentials');}),{status:'unavailable'});
  for(const year of [NaN,2020,2101,2025.5]) assert.equal((await loadPharmacyExport(year,()=>assert.fail())).status,'unavailable');
  for(const selected of ['',[], 'invalid']) assert.equal((await loadPharmacyExport(2025,()=>assert.fail(),selected)).status,'unavailable');
  assert.throws(()=>serializePharmacyCsv({status:'pending'}));
});
test('5000 records is explicit ceiling and never a silently truncated file',async()=>{
  const records=Array.from({length:5000},(_,i)=>row(i));
  assert.equal((await loadPharmacyExport(2025,async()=>envelope(records))).records.length,5000);
  assert.equal((await loadPharmacyExport(2025,async()=>envelope([...records,row(5000)]))).status,'unavailable');
});
test('CSV is UTF-8, semicolon separated, lossless decimal BRL and includes source/scope',async()=>{
  const result=await loadPharmacyExport(2025,async()=>envelope([{...row(1),establishment:'Farmácia "A"; Barreiras'}]));
  const csv=serializePharmacyCsv(result,'2026-09-15T12:00:00.000Z');
  assert.ok(csv.startsWith('\uFEFF'));assert.ok(csv.endsWith('\r\n'));assert.equal(csv.split('\r\n').length,3);
  assert.match(csv,/"Farmácia ""A""; Barreiras"/);
  assert.match(csv,/"999999999999,99"/);assert.doesNotMatch(csv,/1000000000000/);
  assert.match(csv,/"2025-02-07"/);assert.match(csv,/"https:\/\/consultafns.saude.gov.br\/#\/detalhada"/);
  assert.match(csv,/Cobertura parcial/);assert.match(csv,/não é receita da Prefeitura/);
  assert.match(csv,/"2026-09-15T12:00:00.000Z"/);assert.doesNotMatch(csv,/scope_key|CNPJ|register_sha256/);
  const cells=[...csv.split('\r\n')[1].matchAll(/(?:^|;)"((?:[^"]|"")*)"/g)].map(match=>match[1].replaceAll('""','"'));
  assert.equal(cells.length,10);assert.equal(cells[3],'Farmácia "A"; Barreiras');assert.equal(cells[5],'999999999999,99');
});
test('UTF-8 byte ceiling fails before delivering a large CSV, and scientific-looking identifiers remain text',async()=>{
  const id='1e'+'0'.repeat(62);
  const result=await loadPharmacyExport(2025,async()=>envelope([{...row(1),id,sha256:id}]));
  assert.ok(serializePharmacyCsv(result).includes(`"'${id}"`));
  const large=await loadPharmacyExport(2025,async()=>envelope(Array.from({length:5000},(_,i)=>({...row(i),establishment:'漢'.repeat(180)}))));
  assert.equal(large.status,'ready');assert.throws(()=>serializePharmacyCsv(large),/size exceeded/);
  for(const name of ['FARMACIA\nOUTRA','FARMACIA\rOUTRA','\t=1+1']){
    assert.equal((await loadPharmacyExport(2025,async()=>envelope([{...row(1),establishment:name}]))).status,'unavailable');
  }
});
test('text cells neutralize spreadsheet formulas and protect numeric document identifiers',async()=>{
  for(const name of ['=1+1','+1+1','-1+1','@SUM(1;1)','  =1+1','＝1+1','＋1+1','－1+1','＠SUM(1;1)']){
    const result=await loadPharmacyExport(2025,async()=>envelope([{...row(1),establishment:name}]));
    const csv=serializePharmacyCsv(result,'2026-09-15T12:00:00.000Z');
    assert.ok(csv.includes(`"'${name.trim()}"`),name);
    assert.ok(csv.includes(`"'${row(1).id}"`));
    assert.doesNotMatch(csv,/"=""/);
  }
});
test('export links retain only year and establishment, never a page offset',()=>{
  assert.equal(pharmacyExportHref(2025),'\/recursos/saude/exportar?ano=2025');
  assert.equal(pharmacyExportHref(2025,row(1).id),`/recursos/saude/exportar?ano=2025&estabelecimento=${row(1).id}`);
  assert.throws(()=>pharmacyExportHref(2020));assert.throws(()=>pharmacyExportHref(2025,'invalid'));
});
