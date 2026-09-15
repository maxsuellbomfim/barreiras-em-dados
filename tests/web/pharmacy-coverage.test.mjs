import assert from 'node:assert/strict';
import test from 'node:test';
import { loadPharmacyCoverage } from '../../apps/web/lib/pharmacy-coverage.mjs';
const row={year:2021,published_documents:48,establishments:2,first_date:'2021-02-05',last_date:'2021-12-10',status:'partial'};
test('coverage counts the year, not the 25-row page, and allowlists fields',async()=>{
  assert.deepEqual(await loadPharmacyCoverage(2021,async()=>[{...row,private:'SECRET'}]),row);
});
test('pending is not official zero; failed or contradictory coverage is unavailable',async()=>{
  const pending={...row,published_documents:0,establishments:0,first_date:null,last_date:null,status:'pending'};
  assert.deepEqual(await loadPharmacyCoverage(2021,async()=>[pending]),pending);
  for(const bad of [{...row,status:'complete'},{...row,year:2022},{...row,published_documents:-1},
    {...row,establishments:49},{...row,first_date:'2021-02-31'},{...row,last_date:'2020-12-31'},
    {...pending,first_date:row.first_date}]){
    assert.equal((await loadPharmacyCoverage(2021,async()=>[bad])).status,'unavailable');
  }
  assert.equal((await loadPharmacyCoverage(2021,async()=>{throw Error('SECRET');})).status,'unavailable');
});

test('filtered coverage describes one validated selection, not the entire year',async()=>{
  const selected='a'.repeat(64), calls=[];
  const filtered={...row,establishments:1,filter_applied:true,selected_establishment:'Farmácia de teste'};
  const result=await loadPharmacyCoverage(2021,async args=>{calls.push(args);return [filtered];},selected);
  assert.deepEqual(calls,[{p_year:2021,p_establishment_id:selected}]);
  assert.deepEqual(result,filtered);
  for(const bad of [{...filtered,filter_applied:false},{...filtered,selected_establishment:null},
    {...filtered,establishments:2},{...filtered,selected_establishment:'<SECRET>'}]) {
    assert.equal((await loadPharmacyCoverage(2021,async()=>[bad],selected)).status,'unavailable');
  }
  assert.equal((await loadPharmacyCoverage(2021,()=>assert.fail(),'invalid')).status,'unavailable');
});
