import assert from 'node:assert/strict';
import test from 'node:test';
import {loadPharmacyRefresh} from '../../apps/web/lib/pharmacy-refresh.mjs';
const row={year:2026,status:'partial',last_attempt_at:'2026-09-09T01:00:00Z',completed_at:'2026-09-09T01:02:00Z',
 last_verified_at:'2026-09-09T01:02:00Z',verified_documents:17,pending_scopes:2,missing_scopes:1};
test('refresh exposes only dates and validated counts, never errors or originals',async()=>{
 assert.deepEqual(await loadPharmacyRefresh(2026,async()=>[{...row,error:'SECRET',cpf:'SECRET'}]),row);
});
test('never started is distinct from unavailable and from zero',async()=>{
 const never={year:2026,status:'not_started',last_attempt_at:null,completed_at:null,last_verified_at:null,
  verified_documents:null,pending_scopes:null,missing_scopes:null};
 assert.deepEqual(await loadPharmacyRefresh(2026,async()=>[never]),never);
 assert.equal((await loadPharmacyRefresh(2026,async()=>{throw Error('SECRET');})).status,'unavailable');
 for(const bad of [{...row,year:2025},{...row,pending_scopes:-1},{...row,status:'complete'},
  {...row,completed_at:'2026-09-08T01:02:00Z'},{...never,verified_documents:0}])
  assert.equal((await loadPharmacyRefresh(2026,async()=>[bad])).status,'unavailable');
});
