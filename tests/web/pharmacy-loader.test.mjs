import assert from 'node:assert/strict';
import test from 'node:test';
import { loadPharmacyPage } from '../../apps/web/lib/pharmacy-loader.mjs';
const row = {id:'a'.repeat(64), establishment:'FARMACIA TESTE', date:'2025-02-07',amount:'10.00',sha256:'b'.repeat(64),register_sha256:'c'.repeat(64),reviewed_at:'2026-09-08T12:00:00Z',historical_registration_verified:false};
test('pharmacy loader only exposes reviewed RPC allowlist',async()=>{
  const result=await loadPharmacyPage(2025,1,async()=>[{...row,private_note:'SECRET'}]);
  assert.equal(result.publication.status,'ready');
  assert.equal(result.hasNext,false);
  assert.doesNotMatch(JSON.stringify(result),/SECRET|private_note/);
});
test('pharmacy loader distinguishes no approved rows from failure',async()=>{
  assert.equal((await loadPharmacyPage(2025,1,async()=>[])).publication.status,'pending');
  assert.equal((await loadPharmacyPage(2025,1,async()=>{throw Error('secret');})).publication.status,'unavailable');
  assert.equal((await loadPharmacyPage(2025,1,async()=>[{...row,reviewed_at:null}])).publication.status,'unavailable');
});
test('pharmacy pagination bounds scope and probes only full pages',async()=>{
  const calls=[];
  const result=await loadPharmacyPage(2025,2,async args=>{
    calls.push(args);
    return args.p_offset===25 ? Array.from({length:25},(_,i)=>({...row,id:String(i).padStart(64,'0')})) : [];
  });
  assert.deepEqual(calls,[{p_year:2025,p_offset:25},{p_year:2025,p_offset:50}]);
  assert.equal(result.hasNext,false);
  for(const page of [-1,0,402,NaN]) {
    assert.equal((await loadPharmacyPage(2025,page,()=>assert.fail())).publication.status,'unavailable');
  }
});
