import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { PGlite } from '@electric-sql/pglite';

const migration = await readFile(new URL('../../supabase/migrations/20260908173000_fns_pharmacy_registry.sql', import.meta.url), 'utf8');
const key = 'd'.repeat(64);
async function setup() {
  const db = new PGlite();
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema source; create schema raw; create schema api; create schema audit;
    grant usage on schema api, source to anon, authenticated, service_role;
    create function audit.reject_mutation() returns trigger language plpgsql as $$ begin raise exception 'immutable'; end $$;
    create table raw.raw_artifacts(id uuid primary key, sha256 text, source_url text, http_status int, byte_size bigint, content_type text);
    create table raw.raw_records(id uuid primary key, raw_artifact_id uuid references raw.raw_artifacts, record_type text, payload jsonb);
    insert into raw.raw_artifacts values
      ('00000000-0000-0000-0000-000000000001',repeat('a',64),'https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-pagamento?ano=2025',200,100,'application/json'),
      ('00000000-0000-0000-0000-000000000002',repeat('b',64),'https://infoms.saude.gov.br/tempcontent/export/register.xlsx',null,100,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    insert into raw.raw_records values ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','fns_pharmacy_payment',
      '{"document_key":"${key}","document_date":"2025-02-07","net":"10.00","source_row":1,"establishment":"FARMACIA TESTE","register_row":2,"register_sha256":"${'b'.repeat(64)}"}');
  `);
  await db.exec(migration);
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909001000_pharmacy_public_coverage.sql', import.meta.url), 'utf8'));
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909010000_pharmacy_renewal_identity.sql', import.meta.url), 'utf8'));
  await db.exec(await readFile(new URL('../../supabase/migrations/20260915090000_pharmacy_establishment_filter.sql', import.meta.url), 'utf8'));
  await db.exec(await readFile(new URL('../../supabase/migrations/20260915110000_pharmacy_csv_export.sql', import.meta.url), 'utf8'));
  return db;
}
async function snapshot(db, scope='c'.repeat(64), expected=1, establishment='FARMACIA TESTE') {
  const {rows} = await db.query(`insert into source.fns_pharmacy_snapshots(scope_key,payment_year,payment_artifact_id,register_artifact_id,payment_sha256,register_sha256,establishment,expected_documents)
    values ($1,2025,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',repeat('a',64),repeat('b',64),$3,$2) returning id`, [scope,expected,establishment]);
  return rows[0].id;
}
async function document(db, id) {
  await db.query(`insert into source.fns_pharmacy_documents(snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row)
    values ($1,$2,'00000000-0000-0000-0000-000000000003','2025-02-07',10,1,2)`, [id,key]);
}
async function decide(db,id,decision='approved') {
  await db.query(`insert into source.fns_pharmacy_decisions(snapshot_id,decision,reviewer_ref,review_note) values ($1,$2,'operator:test','Private review note not for frontend')`,[id,decision]);
}
const read = db => db.query('select * from api.get_public_pharmacy_payments(2025,0)');
const coverage = async db => (await db.query('select * from api.get_public_pharmacy_coverage(2025)')).rows[0];

const fixtureKey = value => value.toString(16).padStart(64,'0');
let fixtureRecordNumber=0;
async function establishmentFixture(db,{scope,keys,name='FARMACIA HOMONIMA',approved=true,date='2025-02-07'}) {
  const id=await snapshot(db,scope,keys.length,name);
  for(const [index,documentKey] of keys.entries()) {
    const recordId=`00000000-0000-0000-0002-${String(++fixtureRecordNumber).padStart(12,'0')}`;
    await db.query(`insert into raw.raw_records select $1::uuid,raw_artifact_id,record_type,
      payload||jsonb_build_object('document_key',$2::text,'source_row',$3::int,'establishment',$4::text,'document_date',$5::text)
      from raw.raw_records where id='00000000-0000-0000-0000-000000000003'`,[recordId,documentKey,index+1,name,date]);
    await db.query(`insert into source.fns_pharmacy_documents
      (snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row)
      values($1,$2,$3::uuid,$5::date,10,$4,2)`,[id,documentKey,recordId,index+1,date]);
  }
  if(approved) await decide(db,id);
  return id;
}
const filteredPayments=async(db,establishmentId=null,offset=0,year=2025)=>(await db.query(
  'select * from api.get_public_pharmacy_payments_filtered($1,$2,$3)',[year,establishmentId,offset])).rows;
const filteredCoverage=async(db,establishmentId=null,year=2025)=>(await db.query(
  'select * from api.get_public_pharmacy_coverage_filtered($1,$2)',[year,establishmentId])).rows[0];
const establishments=async(db,offset=0,year=2025)=>(await db.query(
  'select * from api.get_public_pharmacy_establishments($1,$2)',[year,offset])).rows;
const invalidSelection={code:'22023',message:'Invalid pharmacy establishment selection'};
const pharmacyExport=async(db,establishmentId=null,year=2025)=>(await db.query(
  'select * from api.get_public_pharmacy_export($1,$2)',[year,establishmentId])).rows;

test('pharmacy export returns one complete envelope beyond the public page size',async()=>{
  const db=await setup();
  try {
    const keys=Array.from({length:25},(_,index)=>fixtureKey(index+1)),other=fixtureKey(26);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[...keys].reverse()});
    await establishmentFixture(db,{scope:'e'.repeat(64),keys:[other],date:'2025-03-01'});
    const rows=await pharmacyExport(db);
    assert.equal(rows.length,1);
    const envelope=rows[0];
    assert.deepEqual({...envelope,records:[]},{year:2025,filter_applied:false,selected_establishment:null,
      published_documents:26,establishments:2,status:'partial',records:[]});
    assert.deepEqual(envelope.records.map(row=>row.id),[other,...keys]);
    const paginated=[];
    for(const offset of [0,25]) {
      const page=await db.query('select to_jsonb(r) as record from api.get_public_pharmacy_payments_filtered(2025,null,$1) r',[offset]);
      paginated.push(...page.rows.map(row=>row.record));
    }
    assert.deepEqual(envelope.records,paginated);
    assert.deepEqual((await db.query('select * from api.get_public_pharmacy_export(2025)')).rows,rows);
    assert.equal(new Set(envelope.records.map(row=>row.id)).size,envelope.published_documents);
  }finally{await db.close();}
});

test('pharmacy export empty publication is a pending envelope, never an official zero',async()=>{
  const db=await setup();
  try {
    const pending={year:2025,filter_applied:false,selected_establishment:null,
      published_documents:0,establishments:0,status:'pending',records:[]};
    assert.deepEqual(await pharmacyExport(db),[pending]);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[fixtureKey(1)],approved:false});
    assert.deepEqual(await pharmacyExport(db),[pending]);
    assert.deepEqual(await pharmacyExport(db,null,2024),[{...pending,year:2024}]);
  }finally{await db.close();}
});

test('pharmacy export selects a reviewed document reference without merging homonymous scopes',async()=>{
  const db=await setup();
  try {
    const first=fixtureKey(1),second=fixtureKey(2),other=fixtureKey(3);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[first,second]});
    await establishmentFixture(db,{scope:'e'.repeat(64),keys:[other]});
    const selected=(await pharmacyExport(db,second))[0];
    assert.equal(selected.filter_applied,true);
    assert.equal(selected.selected_establishment,'FARMACIA HOMONIMA');
    assert.equal(selected.establishments,1);
    assert.equal(selected.published_documents,2);
    assert.equal(selected.status,'partial');
    assert.deepEqual(selected.records.map(row=>row.id),[first,second]);
    assert.deepEqual((await pharmacyExport(db,other))[0].records.map(row=>row.id),[other]);
    assert.equal((await pharmacyExport(db))[0].establishments,2);
  }finally{await db.close();}
});

test('pharmacy export rejects invalid, wrong-year, superseded and revoked selections',async()=>{
  const db=await setup();
  try {
    const token='a'.repeat(64),scope='c'.repeat(64);
    await establishmentFixture(db,{scope,keys:[token]});
    for(const invalid of ['',token.toUpperCase(),'b'.repeat(63),'b'.repeat(65),'b'.repeat(64),scope,"' OR true --"]) {
      await assert.rejects(pharmacyExport(db,invalid),invalidSelection);
    }
    await assert.rejects(pharmacyExport(db,token,2024),invalidSelection);
    for(const year of [null,2020,2101]) await assert.rejects(pharmacyExport(db,null,year),{code:'22023'});
    const replacement=await establishmentFixture(db,{scope,keys:[token],approved:false});
    await assert.rejects(pharmacyExport(db,token),invalidSelection);
    assert.equal((await pharmacyExport(db))[0].status,'pending');
    await decide(db,replacement);
    assert.equal((await pharmacyExport(db,token))[0].published_documents,1);
    await decide(db,replacement,'revoked');
    await assert.rejects(pharmacyExport(db,token),invalidSelection);
    assert.equal((await pharmacyExport(db))[0].published_documents,0);
    await decide(db,replacement);
    await db.exec("update raw.raw_artifacts set sha256=repeat('f',64) where id='00000000-0000-0000-0000-000000000001'");
    await assert.rejects(pharmacyExport(db,token),invalidSelection);
    assert.equal((await pharmacyExport(db))[0].status,'pending');
  }finally{await db.close();}
});

test('pharmacy export applies the global evidence gate before filtering other scopes',async()=>{
  const db=await setup();
  try {
    const shared=fixtureKey(1),unique=fixtureKey(2);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[shared,unique]});
    const duplicate=await establishmentFixture(db,{scope:'e'.repeat(64),keys:[shared],approved:false});
    for(const approved of [false,true]) {
      if(approved) await decide(db,duplicate);
      const envelope=(await pharmacyExport(db))[0];
      assert.equal(envelope.status,'pending');
      assert.equal(envelope.published_documents,0);
      assert.deepEqual(envelope.records,[]);
      // The selected anchor itself is unique, but a different document in its
      // snapshot conflicts with another scope, so filtering must not rescue it.
      await assert.rejects(pharmacyExport(db,unique),invalidSelection);
      await assert.rejects(pharmacyExport(db,shared),invalidSelection);
    }
  }finally{await db.close();}
});

test('pharmacy export permits 5000 real reviewed records and rejects 5001 without a partial envelope',async()=>{
  const db=await setup();
  try {
    // Two hundred legal snapshots, 25 documents each. Keep every ingestion
    // CHECK, lineage trigger, approval guard and the annual gate in this test.
    await db.exec(`
      insert into source.fns_pharmacy_snapshots
        (scope_key,payment_year,payment_artifact_id,register_artifact_id,payment_sha256,register_sha256,establishment,expected_documents)
      select lpad(to_hex(n+10000),64,'0'),2025,'00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000002',repeat('a',64),repeat('b',64),'FARMACIA LIMITE',25
      from generate_series(1,200) n;
      insert into raw.raw_records
      select md5('pharmacy-export-limit-'||n)::uuid,r.raw_artifact_id,r.record_type,
        r.payload||jsonb_build_object('document_key',lpad(to_hex(n+100000),64,'0'),
          'source_row',(n-1)%25+1,'establishment','FARMACIA LIMITE')
      from generate_series(1,5000) n cross join raw.raw_records r
      where r.id='00000000-0000-0000-0000-000000000003';
      insert into source.fns_pharmacy_documents
        (snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row)
      select s.id,lpad(to_hex(n+100000),64,'0'),md5('pharmacy-export-limit-'||n)::uuid,
        '2025-02-07',10,(n-1)%25+1,2
      from generate_series(1,5000) n join source.fns_pharmacy_snapshots s
        on s.scope_key=lpad(to_hex((n-1)/25+10001),64,'0');
      insert into source.fns_pharmacy_decisions(snapshot_id,decision,reviewer_ref,review_note)
      select id,'approved','operator:test','Private review note not for frontend'
      from source.fns_pharmacy_snapshots;
    `);
    const rows=await pharmacyExport(db);
    assert.equal(rows.length,1);
    assert.equal(rows[0].published_documents,5000);
    assert.equal(rows[0].establishments,200);
    assert.equal(rows[0].records.length,5000);
    assert.equal(new Set(rows[0].records.map(row=>row.id)).size,5000);
    assert.equal(rows[0].status,'partial');
    await establishmentFixture(db,{scope:'f'.repeat(64),keys:[fixtureKey(900000)]});
    await assert.rejects(pharmacyExport(db),{code:'54000',message:'Pharmacy export exceeds 5000 records'});
    const selected=(await pharmacyExport(db,fixtureKey(100001)))[0];
    assert.equal(selected.records.length,25);
    assert.equal(selected.published_documents,25);
    assert.equal(selected.establishments,1);
    await assert.rejects(snapshot(db,'e'.repeat(64),26),{code:'23514'});
  }finally{await db.close();}
});

test('pharmacy export exposes only public fields and explicit public RPC grants',async()=>{
  const db=await setup();
  try {
    const token=fixtureKey(1);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[token]});
    await db.exec('create role pharmacy_export_unprivileged; grant usage on schema api to pharmacy_export_unprivileged');
    for(const role of ['anon','authenticated']) {
      await db.exec(`set role ${role}`);
      const envelope=(await pharmacyExport(db,token))[0];
      assert.deepEqual(Object.keys(envelope).sort(),['year','filter_applied','selected_establishment',
        'published_documents','establishments','status','records'].sort());
      assert.deepEqual(Object.keys(envelope.records[0]).sort(),['id','establishment','date','amount',
        'sha256','register_sha256','reviewed_at','historical_registration_verified'].sort());
      assert.equal(envelope.records[0].historical_registration_verified,false);
      assert.doesNotMatch(JSON.stringify(envelope),
        /scope_key|snapshot_id|raw_record_id|register_row|register_page|review_note|reviewer_ref|Private review|CNPJ|cnpj/);
      await assert.rejects(db.query('select * from source.filtered_pharmacy_rows(2025,null)'),/permission denied/);
      await assert.rejects(db.query('select * from source.fns_pharmacy_decisions'),/permission denied/);
      await db.exec('reset role');
    }
    for(const role of ['service_role','pharmacy_export_unprivileged']) {
      await db.exec(`set role ${role}`);
      await assert.rejects(pharmacyExport(db,token),/permission denied/);
      await db.exec('reset role');
    }
    const {rows:[definition]}=await db.query(`select p.provolatile,p.prosecdef,p.proconfig,pg_get_functiondef(p.oid) as body
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
      where n.nspname='api' and p.proname='get_public_pharmacy_export'`);
    assert.equal(definition.provolatile,'s');
    assert.equal(definition.prosecdef,true);
    assert.deepEqual(definition.proconfig,['search_path=""']);
    assert.equal((definition.body.match(/source\.filtered_pharmacy_rows\(/g)||[]).length,1);
    assert.match(definition.body,/as materialized/i);
  }finally{await db.close();}
});

test('pharmacy establishment filter exposes reviewed opaque options and keeps homonyms separate',async()=>{
  const db=await setup();
  try {
    assert.deepEqual(await establishments(db),[]);
    assert.deepEqual(await filteredCoverage(db),{year:2025,published_documents:0,establishments:0,
      first_date:null,last_date:null,status:'pending',selected_establishment:null,filter_applied:false});
    const first=fixtureKey(1),second=fixtureKey(2),other=fixtureKey(3);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[first,second]});
    await establishmentFixture(db,{scope:'e'.repeat(64),keys:[other]});
    assert.deepEqual(await establishments(db),[
      {establishment_id:first,establishment:'FARMACIA HOMONIMA'},
      {establishment_id:other,establishment:'FARMACIA HOMONIMA'}
    ]);
    // A currently reviewed document remains a selector even when it is not the minimum option id.
    assert.deepEqual((await filteredPayments(db,second)).map(row=>row.id),[first,second]);
    assert.deepEqual((await filteredPayments(db,other)).map(row=>row.id),[other]);
    assert.deepEqual(await filteredCoverage(db,second),{year:2025,published_documents:2,establishments:1,
      first_date:new Date('2025-02-07T00:00:00.000Z'),last_date:new Date('2025-02-07T00:00:00.000Z'),status:'partial',
      selected_establishment:'FARMACIA HOMONIMA',filter_applied:true});
    assert.equal((await filteredCoverage(db)).published_documents,3);
    assert.equal((await filteredCoverage(db)).establishments,2);
    assert.equal((await filteredCoverage(db)).selected_establishment,null);
    assert.equal((await filteredCoverage(db)).filter_applied,false);
    assert.deepEqual(await filteredPayments(db),(await read(db)).rows);
    assert.deepEqual((await db.query('select * from api.get_public_pharmacy_payments_filtered(2025)')).rows,
      (await read(db)).rows);
    assert.deepEqual((await db.query('select * from api.get_public_pharmacy_establishments(2025)')).rows,
      await establishments(db));
    assert.deepEqual((await db.query('select * from api.get_public_pharmacy_coverage_filtered(2025)')).rows[0],
      await filteredCoverage(db));
  }finally{await db.close();}
});

test('pharmacy establishment filter paginates real ingestion limits with the same filtered counts',async()=>{
  const db=await setup();
  try {
    const keys=Array.from({length:25},(_,index)=>fixtureKey(index+1)),other=fixtureKey(26);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys,name:'FARMACIA A'});
    await establishmentFixture(db,{scope:'e'.repeat(64),keys:[other],name:'FARMACIA B'});
    // The importer still limits one snapshot to 25 documents; this test does not relax its CHECKs.
    const first=await filteredPayments(db),second=await filteredPayments(db,null,25);
    assert.equal(first.length,25);assert.equal(second.length,1);
    assert.equal(new Set([...first,...second].map(row=>row.id)).size,26);
    assert.equal((await filteredCoverage(db)).published_documents,26);
    assert.equal((await filteredPayments(db,keys[24])).length,25);
    assert.deepEqual(await filteredPayments(db,keys[24],25),[]);
    assert.equal((await filteredCoverage(db,keys[24])).published_documents,25);
    assert.deepEqual((await filteredPayments(db,other)).map(row=>row.id),[other]);
    assert.equal((await filteredCoverage(db,other)).published_documents,1);
    assert.deepEqual(await filteredPayments(db,other,10000),[]);
    assert.equal((await filteredCoverage(db,other)).status,'partial');
  }finally{await db.close();}
});

test('pharmacy establishment filter options are bounded, deterministic and not grouped by name',async()=>{
  const db=await setup();
  try {
    for(let index=1;index<=26;index++) {
      await establishmentFixture(db,{scope:fixtureKey(index+100),keys:[fixtureKey(index)],
        name:index===26?'FARMACIA A':'FARMACIA HOMONIMA'});
    }
    const first=await establishments(db),second=await establishments(db,25);
    assert.equal(first.length,25);assert.equal(second.length,1);
    assert.equal(first[0].establishment,'FARMACIA A');
    assert.deepEqual([...first,...second].map(row=>row.establishment_id),
      [fixtureKey(26),...Array.from({length:25},(_,index)=>fixtureKey(index+1))]);
    assert.equal(new Set([...first,...second].map(row=>row.establishment_id)).size,26);
    assert.deepEqual(await establishments(db,50),[]);
    assert.deepEqual(await establishments(db,10000),[]);
    // Resolution is against the complete reviewed year, not the current 25-option page.
    assert.equal((await filteredCoverage(db,second[0].establishment_id)).published_documents,1);
    assert.equal((await filteredPayments(db,second[0].establishment_id)).length,1);
  }finally{await db.close();}
});

test('pharmacy establishment filter never restores old snapshots or revoked selections',async()=>{
  const db=await setup();
  try {
    const original=fixtureKey(2),newMinimum=fixtureKey(1),scope='c'.repeat(64);
    await establishmentFixture(db,{scope,keys:[original]});
    assert.equal((await establishments(db))[0].establishment_id,original);
    const replacement=await establishmentFixture(db,{scope,keys:[original,newMinimum],approved:false});
    assert.deepEqual(await establishments(db),[]);
    assert.deepEqual(await filteredPayments(db),[]);
    assert.equal((await filteredCoverage(db)).status,'pending');
    await assert.rejects(filteredPayments(db,original),invalidSelection);
    await assert.rejects(filteredCoverage(db,original),invalidSelection);
    await decide(db,replacement);
    assert.equal((await establishments(db))[0].establishment_id,newMinimum);
    assert.equal((await filteredPayments(db,original)).length,2);
    assert.equal((await filteredCoverage(db,original)).published_documents,2);
    await decide(db,replacement,'revoked');
    assert.deepEqual(await establishments(db),[]);
    assert.deepEqual(await filteredPayments(db),[]);
    await assert.rejects(filteredPayments(db,original),invalidSelection);
    await assert.rejects(filteredCoverage(db,newMinimum),invalidSelection);
    await decide(db,replacement);
    await db.exec("update raw.raw_artifacts set sha256=repeat('f',64) where id='00000000-0000-0000-0000-000000000001'");
    assert.deepEqual(await establishments(db),[]);
    await assert.rejects(filteredPayments(db,original),invalidSelection);
    await assert.rejects(filteredCoverage(db,original),invalidSelection);
  }finally{await db.close();}
});

test('pharmacy establishment filter cannot bypass the year-global duplicate gate',async()=>{
  const db=await setup();
  try {
    const shared=fixtureKey(1),unique=fixtureKey(2);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[shared,unique]});
    const duplicate=await establishmentFixture(db,{scope:'e'.repeat(64),keys:[shared],approved:false});
    for(const approved of [false,true]) {
      if(approved) await decide(db,duplicate);
      assert.deepEqual(await establishments(db),[]);
      assert.deepEqual(await filteredPayments(db),[]);
      assert.equal((await filteredCoverage(db)).published_documents,0);
      // Even the nonduplicated anchor is hidden when another row invalidates its snapshot.
      for(const token of [shared,unique]) {
        await assert.rejects(filteredPayments(db,token),invalidSelection);
        await assert.rejects(filteredCoverage(db,token),invalidSelection);
      }
    }
  }finally{await db.close();}
});

test('pharmacy establishment filter rejects invalid scope and never broadens an unknown selection',async()=>{
  const db=await setup();
  try {
    const token='a'.repeat(64),scope='c'.repeat(64);
    await establishmentFixture(db,{scope,keys:[token]});
    for(const invalid of ['',token.toUpperCase(),'b'.repeat(63),'b'.repeat(65),'b'.repeat(64),scope,"' OR true --"]) {
      await assert.rejects(filteredPayments(db,invalid),{code:'22023'});
      await assert.rejects(filteredCoverage(db,invalid),{code:'22023'});
    }
    await assert.rejects(filteredPayments(db,token,0,2024),invalidSelection);
    await assert.rejects(filteredCoverage(db,token,2024),invalidSelection);
    assert.deepEqual(await establishments(db,0,2024),[]);
    assert.deepEqual(await filteredPayments(db,null,0,2024),[]);
    assert.equal((await filteredCoverage(db,null,2024)).status,'pending');
    for(const year of [null,2020,2101]) {
      await assert.rejects(filteredPayments(db,null,0,year),{code:'22023'});
      await assert.rejects(filteredCoverage(db,null,year),{code:'22023'});
      await assert.rejects(establishments(db,0,year),{code:'22023'});
    }
    for(const offset of [null,-1,10001]) {
      await assert.rejects(filteredPayments(db,token,offset),{code:'22023'});
      await assert.rejects(establishments(db,offset),{code:'22023'});
    }
    assert.equal((await filteredPayments(db)).length,1);
    assert.equal((await filteredCoverage(db,token)).published_documents,1);
  }finally{await db.close();}
});

test('pharmacy establishment filter preserves private fields and explicit public RPC grants',async()=>{
  const db=await setup();
  try {
    const token=fixtureKey(1);
    await establishmentFixture(db,{scope:'c'.repeat(64),keys:[token]});
    await db.exec('create role pharmacy_unprivileged; grant usage on schema api to pharmacy_unprivileged');
    for(const role of ['anon','authenticated']) {
      await db.exec(`set role ${role}`);
      const rows=await filteredPayments(db,token),options=await establishments(db),counts=await filteredCoverage(db,token);
      assert.equal(rows.length,1);assert.equal(options.length,1);assert.equal(counts.published_documents,1);
      assert.deepEqual(Object.keys(rows[0]).sort(),[
        'id','establishment','date','amount','sha256','register_sha256','reviewed_at','historical_registration_verified'].sort());
      assert.deepEqual(Object.keys(options[0]).sort(),['establishment_id','establishment'].sort());
      assert.deepEqual(Object.keys(counts).sort(),['year','published_documents','establishments','first_date','last_date',
        'status','selected_establishment','filter_applied'].sort());
      assert.doesNotMatch(JSON.stringify({rows,options,counts}),
        /scope_key|snapshot_id|raw_record_id|register_row|register_page|review_note|reviewer_ref|Private review|CNPJ|cnpj/);
      await assert.rejects(db.query('select * from source.filtered_pharmacy_rows(2025,null)'),/permission denied/);
      await assert.rejects(db.query('select * from source.reviewed_pharmacy_rows(2025)'),/permission denied/);
      await assert.rejects(db.query('select * from source.fns_pharmacy_snapshots'),/permission denied/);
      await db.exec('reset role');
    }
    for(const role of ['service_role','pharmacy_unprivileged']) {
      await db.exec(`set role ${role}`);
      await assert.rejects(filteredPayments(db,token),/permission denied/);
      await assert.rejects(filteredCoverage(db,token),/permission denied/);
      await assert.rejects(establishments(db),/permission denied/);
      if(role==='service_role') await assert.rejects(db.query('select * from source.filtered_pharmacy_rows(2025,null)'),/permission denied/);
      await db.exec('reset role');
    }
  }finally{await db.close();}
});

test('refresh approval is atomic, replayable and unavailable to public roles',async()=>{
 const db=await setup();
 try {
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909040000_pharmacy_refresh_guard.sql',import.meta.url),'utf8'));
  const before=await snapshot(db); await document(db,before); await decide(db,before);
  const after=await snapshot(db); await document(db,after);
  const approve=()=>db.query('select source.approve_pharmacy_refresh($1,$2) as id',[before,after]);
  const first=(await approve()).rows[0].id;
  assert.equal((await approve()).rows[0].id,first);
  assert.equal((await read(db)).rows.length,1);
  assert.equal((await db.query('select count(*)::int n from source.fns_pharmacy_decisions')).rows[0].n,2);
  await decide(db,before,'revoked');
  await assert.rejects(approve(),/baseline/);
  await db.exec('set role anon');
  await assert.rejects(approve(),/permission denied/);
 }finally{await db.close();}
});

test('refresh refuses superseded baseline and another scope',async()=>{
 const db=await setup();
 try {
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909040000_pharmacy_refresh_guard.sql',import.meta.url),'utf8'));
  const before=await snapshot(db); await document(db,before); await decide(db,before);
  const middle=await snapshot(db); await document(db,middle);
  const after=await snapshot(db); await document(db,after);
  await assert.rejects(db.query('select source.approve_pharmacy_refresh($1,$2)',[before,after]),/baseline/);
  const other=await snapshot(db,'e'.repeat(64)); await document(db,other);
  await assert.rejects(db.query('select source.approve_pharmacy_refresh($1,$2)',[before,other]),/scope/);
 }finally{await db.close();}
});

for(const mode of ['added','changed','removed']) test(`refresh ${mode} documents without silent replacement`,async()=>{
 const db=await setup();
 try {
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909040000_pharmacy_refresh_guard.sql',import.meta.url),'utf8'));
  const before=await snapshot(db); await document(db,before); await decide(db,before);
  const after=await snapshot(db,'c'.repeat(64),mode==='added'?2:1);
  const newKey=mode==='changed'?key:'e'.repeat(64), amount=mode==='changed'?'12.00':'10.00', row=mode==='added'?2:1;
  await db.query(`insert into raw.raw_records select '00000000-0000-0000-0000-000000000004',raw_artifact_id,record_type,payload||jsonb_build_object('document_key',$1::text,'net',$2::text,'source_row',$3::int) from raw.raw_records where id='00000000-0000-0000-0000-000000000003'`,[newKey,amount,row]);
  if(mode==='added') await document(db,after);
  await db.query(`insert into source.fns_pharmacy_documents(snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row) values($1,$2,'00000000-0000-0000-0000-000000000004','2025-02-07',$3,$4,2)`,[after,newKey,amount,row]);
  const approve=()=>db.query('select source.approve_pharmacy_refresh($1,$2)',[before,after]);
  if(mode==='added') {await approve();assert.equal((await read(db)).rows.length,2);}
  else {await assert.rejects(approve(),/changed or removed/);assert.equal((await read(db)).rows.length,0);}
 }finally{await db.close();}
});

test('renewal PDF requires official source, HTTP 200 and matching page; stays private',async()=>{
  const db=await setup();
  try {
    await db.exec(`update raw.raw_artifacts set source_url='https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/renovacao-de-estabelecimentos-participantes/empresas-credenciadas-para-realizar-a-renovacao-2025/@@download/file',content_type='application/pdf',http_status=200 where id='00000000-0000-0000-0000-000000000002';
      update raw.raw_records set payload=payload||'{"register_page":44,"register_row":1}';`);
    const id=await snapshot(db);
    await db.query(`insert into source.fns_pharmacy_documents(snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row,register_page)
      values($1,$2,'00000000-0000-0000-0000-000000000003','2025-02-07',10,1,1,44)`,[id,key]);
    await decide(db,id);
    assert.equal((await read(db)).rows.length,1);
    assert.doesNotMatch(JSON.stringify((await read(db)).rows),/register_page|scope_key/);
    for(const bad of ["http_status=null", "source_url='https://example.com/register.pdf'"]){
      await db.exec('begin');
      await db.exec(`update raw.raw_artifacts set ${bad} where id='00000000-0000-0000-0000-000000000002'`);
      assert.equal((await read(db)).rows.length,0);
      await db.exec('rollback');
    }
    await db.exec(`update raw.raw_records set payload=payload||'{"register_page":45}'`);
    assert.equal((await coverage(db)).published_documents,0);
  } finally {await db.close();}
});

test('pharmacy pending, approved, revoked and new snapshot never fall back', async () => {
  const db=await setup();
  try {
    const id=await snapshot(db); await document(db,id);
    assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).status,'pending');
    await decide(db,id);
    await db.exec('set role anon');
    const rows=(await read(db)).rows;
    assert.equal(rows.length,1); assert.equal(rows[0].amount,'10.00');
    assert.equal(rows[0].historical_registration_verified,false);
    assert.equal((await coverage(db)).published_documents,1);
    assert.equal((await coverage(db)).status,'partial');
    assert.doesNotMatch(JSON.stringify(rows), /review_note|Private review|raw_record_id|scope_key|snapshot_id/);
    await assert.rejects(db.query('select * from source.fns_pharmacy_documents'), /permission denied/);
    await db.exec('reset role');
    await decide(db,id,'revoked'); assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).published_documents,0);
    await decide(db,id); assert.equal((await read(db)).rows.length,1);
    await snapshot(db); assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).status,'pending');
  } finally { await db.close(); }
});

test('pharmacy approval requires complete evidence; immutable decisions seal documents',async()=>{
  const db=await setup();
  try {
    const id=await snapshot(db);
    await assert.rejects(decide(db,id),/incomplete|evidence/i);
    await document(db,id); await decide(db,id);
    await assert.rejects(document(db,id),/sealed/i);
    await assert.rejects(db.query('delete from source.fns_pharmacy_decisions'),/immutable/);
    await db.exec("update raw.raw_artifacts set sha256=repeat('f',64) where id='00000000-0000-0000-0000-000000000001'");
    assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).published_documents,0);
    await assert.rejects(db.query('select * from api.get_public_pharmacy_payments(2025,-1)'),/Invalid/);
  } finally { await db.close(); }
});

test('pharmacy duplicated document across scopes is excluded, never doubled',async()=>{
  const db=await setup();
  try {
    for(const scope of ['c','e']) { const id=await snapshot(db,scope.repeat(64)); await document(db,id); await decide(db,id); }
    assert.equal((await read(db)).rows.length,0);
    await db.exec('set role service_role');
    await assert.rejects(db.query('select * from source.fns_pharmacy_snapshots'),/permission denied/);
  } finally { await db.close(); }
});

test('pharmacy raw lineage mismatches are rejected and pagination is bounded',async()=>{
  const db=await setup();
  try {
    const first=await snapshot(db);
    await db.exec("update raw.raw_records set payload=jsonb_set(payload,'{net}','\"11.00\"')");
    await assert.rejects(document(db,first),/mismatch/);
    await db.exec("update raw.raw_records set payload=jsonb_set(payload,'{net}','\"10.00\"')");
    await document(db,first); await decide(db,first);
    for(let i=1;i<=25;i++) {
      const docKey=i.toString(16).padStart(64,'0');
      const recordId=`00000000-0000-0000-0001-${String(i).padStart(12,'0')}`;
      await db.query(`insert into raw.raw_records select $1::uuid,raw_artifact_id,record_type,
        jsonb_set(payload,'{document_key}',to_jsonb($2::text)) from raw.raw_records
        where id='00000000-0000-0000-0000-000000000003'`,[recordId,docKey]);
      const id=await snapshot(db,docKey);
      await db.query(`insert into source.fns_pharmacy_documents values($1,$2,$3::uuid,'2025-02-07',10,1,2)`,[id,docKey,recordId]);
      await decide(db,id);
    }
    const page1=(await read(db)).rows;
    const page2=(await db.query('select * from api.get_public_pharmacy_payments(2025,25)')).rows;
    assert.equal(page1.length,25); assert.equal(page2.length,1);
    assert.equal(new Set([...page1,...page2].map(r=>r.id)).size,26);
    assert.equal((await coverage(db)).published_documents,26);
    assert.equal((await coverage(db)).establishments,26);
    await assert.rejects(db.query('select * from api.get_public_pharmacy_coverage(2020)'),/Invalid/);
    assert.equal((await db.query('select * from api.get_public_pharmacy_payments(2024,0)')).rows.length,0);
  } finally { await db.close(); }
});
