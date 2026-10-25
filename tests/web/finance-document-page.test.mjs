import assert from 'node:assert/strict';
import test from 'node:test';
import { getPublicFinanceDocumentPage } from '../../apps/web/lib/finance-documents.ts';

test('consulta financeira envia ano e página ao servidor; falha não vira lista vazia', async t => {
  const saved = { url:process.env.PUBLIC_DATA_SUPABASE_URL, key:process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY };
  process.env.PUBLIC_DATA_SUPABASE_URL='https://example.test';
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY='sb_publishable_test';
  t.after(()=>{
    for(const [name,value] of [['PUBLIC_DATA_SUPABASE_URL',saved.url],['PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY',saved.key]]){
      if(value===undefined) delete process.env[name]; else process.env[name]=value;
    }
  });
  const requests=[];
  let payload=[{total_count:0,available_years:[2026,2021],items:[]}];
  t.mock.method(globalThis,'fetch',async (url,options)=>{
    requests.push({url,body:JSON.parse(options.body)}); return Response.json(payload);
  });
  assert.equal((await getPublicFinanceDocumentPage(2021,'rreo',9)).state,'available');
  assert.deepEqual(requests[0].body,{page_size:25,page_number:9,year_filter:2021,resource_filter:'rreo'});
  assert.match(requests[0].url,/get_public_finance_document_page$/);
  payload=[{total_count:201,available_years:[2021],items:[]}];
  assert.equal((await getPublicFinanceDocumentPage(2021,'rreo',1)).state,'unavailable');
  payload=[{total_count:0,available_years:[2021],items:[null]}];
  assert.equal((await getPublicFinanceDocumentPage()).state,'unavailable');
  const count=requests.length;
  assert.equal((await getPublicFinanceDocumentPage(2021,'unsafe',1)).state,'unavailable');
  assert.equal(requests.length,count);
});
