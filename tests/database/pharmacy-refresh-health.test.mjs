import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {PGlite} from '@electric-sql/pglite';

test('pharmacy update health excludes imports, private details and invalid success',async()=>{
 const db=new PGlite();
 try {
  await db.exec(`create role anon;create role authenticated;create role service_role;
   create schema source;create schema api;
   create table source.data_sources(id int,slug text);
   create table source.source_endpoints(id int,data_source_id int,slug text);
   create table source.collection_runs(id int,source_endpoint_id int,collector_version text,
    collection_window_start date,collection_window_end date,status text,started_at timestamptz,
    completed_at timestamptz,metrics jsonb);
   insert into source.data_sources values(1,'fns-farmacia-popular');
   insert into source.source_endpoints values(1,1,'payment');`);
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909060000_pharmacy_refresh_health.sql',import.meta.url),'utf8'));
  const read=async()=>(await db.query('select * from api.get_public_pharmacy_refresh(2026)')).rows[0];
  assert.equal((await read()).status,'not_started');
  await db.exec(`insert into source.collection_runs values(1,1,'fns-pharmacy-import/1.0.0','2026-01-01','2026-12-31','succeeded','2026-09-08','2026-09-08','{}');`);
  assert.equal((await read()).status,'not_started');
  const metrics={control_plane:true,collection_outcome:'partial',status:'partial',verified_documents:17,pending_scopes:2,missing_scopes:1};
  await db.query(`insert into source.collection_runs values(2,1,'pharmacy-refresh/1.0.0','2026-01-01','2026-12-31','partial','2026-09-09T01:00Z','2026-09-09T01:02Z',$1)`,[JSON.stringify({...metrics,secret:'DO_NOT_EXPOSE'})]);
  let row=await read();
  assert.equal(row.status,'partial'); assert.equal(row.pending_scopes,2); assert.equal(row.missing_scopes,1);
  assert.equal(row.verified_documents,17);assert.ok(row.last_verified_at);
  assert.equal(JSON.stringify(row).includes('DO_NOT_EXPOSE'),false);
  await db.exec(`insert into source.collection_runs values(3,1,'pharmacy-refresh/1.0.0','2026-01-01','2026-12-31','failed','2026-09-10','2026-09-10','{"control_plane":true}');`);
  row=await read();assert.equal(row.status,'failed');assert.equal(row.pending_scopes,null);assert.ok(row.last_verified_at);
  await db.exec(`update source.collection_runs set status='succeeded',metrics='{"control_plane":true,"collection_outcome":"complete"}' where id=3;`);
  assert.equal((await read()).status,'unavailable');
  await db.exec('set role anon');
  assert.equal((await read()).status,'unavailable');
  await assert.rejects(db.exec('select * from source.collection_runs'),/permission denied/);
 } finally {await db.close();}
});
