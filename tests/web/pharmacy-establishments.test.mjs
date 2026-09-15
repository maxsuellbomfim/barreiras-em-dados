import assert from 'node:assert/strict';
import test from 'node:test';
import {loadPharmacyEstablishments,pharmacyHref} from '../../apps/web/lib/pharmacy-establishments.mjs';
const option=i=>({establishment_id:i.toString(16).padStart(64,'0'),establishment:'Mesmo nome'});

test('options are paginated metadata, retain homonyms, and omit private fields',async()=>{
  const calls=[];
  const result=await loadPharmacyEstablishments(2025,1,async args=>{
    calls.push(args);
    return args.p_offset===0?Array.from({length:25},(_,i)=>({...option(i),scope_key:'PRIVATE'})):[option(25)];
  });
  assert.equal(result.status,'ready'); assert.equal(result.records.length,25); assert.equal(result.hasNext,true);
  assert.equal(new Set(result.records.map(r=>r.establishment_id)).size,25);
  assert.doesNotMatch(JSON.stringify(result),/PRIVATE|scope_key/);
  assert.deepEqual(calls,[{p_year:2025,p_offset:0},{p_year:2025,p_offset:25}]);
});

test('invalid options and out of range pages fail closed, empty stays limited to that page',async()=>{
  for(const rows of [[option(1),option(1)],[{...option(1),establishment_id:'bad'}],
    [{...option(1),establishment:'<private>'}],Array.from({length:26},(_,i)=>option(i)),null]){
    assert.equal((await loadPharmacyEstablishments(2025,1,async()=>rows)).status,'unavailable');
  }
  for(const page of [0,402,1.5]) assert.equal((await loadPharmacyEstablishments(2025,page,()=>assert.fail())).status,'unavailable');
  assert.deepEqual(await loadPharmacyEstablishments(2025,2,async()=>[]),{status:'ready',records:[],hasNext:false});
});

test('pagination retains year and selection; reset is explicit, invalid filters are not dropped',()=>{
  const selected=option(1).establishment_id;
  assert.equal(pharmacyHref(2025,{page:2,establishment:selected,optionsPage:3}),`?ano=2025&estabelecimento=${selected}&pagina=2&opcoes=3`);
  assert.equal(pharmacyHref(2025,{establishment:selected}),`?ano=2025&estabelecimento=${selected}`);
  assert.equal(pharmacyHref(2026),'?ano=2026');
  assert.throws(()=>pharmacyHref(2025,{establishment:'bad'}));
});
