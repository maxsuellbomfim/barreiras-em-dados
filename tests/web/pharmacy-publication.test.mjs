import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { readPharmacyPublication } from '../../apps/web/lib/pharmacy-publication.mjs';

const publication = () => ({approved:true, evidenceCurrent:true, year:2025, records:[{
  id:'record-1', establishment:'Estabelecimento de teste', date:'2025-02-07',
  amount:'10.00', sha256:'a'.repeat(64), identityVerified:true,
  reconciliation:'standalone_fns', program:'FARMACIA POPULAR',
  municipality:'290320', beneficiaryType:'institution', account:'SECRET',
}]});
test('official renewal source is accessible without implying historical accreditation',async()=>{
 const source=await readFile(new URL('../../apps/web/app/recursos/saude/pharmacy-payments.tsx',import.meta.url),'utf8');
 assert.ok(source.includes('empresas-credenciadas-para-realizar-a-renovacao-2025/view'));
 assert.ok(source.includes('A lista de renovação de 2025 ajuda a conferir a identidade'));
});
test('unpublished is pending, never official zero',()=>{
  assert.deepEqual(readPharmacyPublication(null),{status:'pending',records:[]});
});
test('allowlist omits private fields and no combined total is produced',()=>{
  const result=readPharmacyPublication(publication());
  assert.equal(result.status,'ready');
  assert.equal(result.records.length,1);
  assert.ok(!JSON.stringify(result).includes('SECRET'));
  assert.ok(!('total' in result));
});
test('stale evidence, unknown identity, judicial records and duplicate ids block all',()=>{
  for(const mutate of [p=>p.approved=false,p=>p.evidenceCurrent=false,
    p=>p.records[0].identityVerified=false,p=>p.records[0].program='DEMANDAS JUDICIAIS',
    p=>p.records.push({...p.records[0]}),p=>p.records[0].amount='NaN',
    p=>p.records[0].municipality='1',p=>p.records[0].date='2025-02-31']){
    const p=publication();mutate(p);
    assert.equal(readPharmacyPublication(p).status,'unavailable');
  }
});
