import test from 'node:test';
import assert from 'node:assert/strict';
import { auditContractInventory } from '../../scripts/audit-pncp-contract-inventory.mjs';

const own='13654405000195';
const contract=`${own}-2-000023/2026`;
const parent='13250888000162-1-000003/2026';
const window={since:'20260101',until:'20260915'};
const row=()=>({numeroControlePNCP:contract,numeroControlePncpCompra:parent,orgaoEntidade:{cnpj:own},dataPublicacaoPncp:'2026-06-11T09:42:23'});
const page=()=>({data:[row()],totalRegistros:1,totalPaginas:1,numeroPagina:1,paginasRestantes:0,empty:false});

test('detects own contract with external procurement instead of dropping it',()=>{
  const result=auditContractInventory(page(),[],window);
  assert.equal(result.gate,'REVIEW');
  assert.deepEqual(result.missing_contracts,[contract]);
  assert.deepEqual(result.cross_organization_links,[{contract,procurement:parent}]);
  assert.equal(result.publication_authorized,false);
});
test('compares official keys, not year embedded in contract or position',()=>{
  const p=page(); p.data[0].numeroControlePNCP=`${own}-2-000153/2024`;
  p.data[0].numeroControlePncpCompra=`${own}-1-000083/2024`;
  const result=auditContractInventory(p,[{contract_control:p.data[0].numeroControlePNCP,procurement_control:p.data[0].numeroControlePncpCompra}],window);
  assert.equal(result.gate,'MATCH'); assert.equal(result.source_contracts,1);
});
test('keeps cross-organization and mismatched links in review even if contract exists',()=>{
  const result=auditContractInventory(page(),[{contract_control:contract,procurement_control:`${own}-1-000003/2026`}],window);
  assert.equal(result.gate,'REVIEW'); assert.equal(result.link_conflicts.length,1);
});
test('fails closed for incomplete pages and contradictory metadata',()=>{
  for(const patch of [{totalPaginas:2},{numeroPagina:2},{paginasRestantes:1},{totalRegistros:2},{totalRegistros:'1'},{empty:true}])
    assert.throws(()=>auditContractInventory({...page(),...patch},[],window));
});
test('rejects foreign contracts, dates outside range, malformed or repeated IDs',()=>{
  for(const patch of [{orgaoEntidade:{cnpj:'13250888000162'}},{numeroControlePNCP:'13250888000162-2-000023/2026'},{dataPublicacaoPncp:'2025-12-31T00:00:00'},{dataPublicacaoPncp:'2026-02-30T00:00:00'},{numeroControlePncpCompra:null}]) {
    const p=page(); Object.assign(p.data[0],patch); assert.throws(()=>auditContractInventory(p,[],window));
  }
  const p=page();p.data.push(row());p.totalRegistros=2;assert.throws(()=>auditContractInventory(p,[],window));
});
test('rejects duplicate inventory and never leaks raw fields or amounts',()=>{
  const inventory=[{contract_control:contract,procurement_control:parent}];
  assert.throws(()=>auditContractInventory(page(),[...inventory,...inventory],window));
  const p=page();p.data[0].niFornecedor='PRIVATE_SENTINEL';p.data[0].valorGlobal=28780;
  const output=JSON.stringify(auditContractInventory(p,inventory,window));
  assert.ok(!output.includes('PRIVATE_SENTINEL'));assert.ok(!output.includes('28780'));
});
test('empty official page describes only the requested publication window',()=>{
  const result=auditContractInventory({data:[],totalRegistros:0,totalPaginas:0,numeroPagina:1,paginasRestantes:0,empty:true},[],window);
  assert.equal(result.gate,'MATCH');assert.equal(result.scope,'publication_window_inventory');
  assert.equal(result.publication_authorized,false);
});
