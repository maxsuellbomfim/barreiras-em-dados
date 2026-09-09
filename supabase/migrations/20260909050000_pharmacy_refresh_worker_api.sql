begin;
-- Dedicated worker surface: no direct access to decisions or private tables.
-- Original bytes must still be rehashed/reconciled by the authorized worker.
create function source.import_pharmacy_refresh(p jsonb)
returns void language plpgsql security definer set search_path='' as $worker$
declare
  a jsonb; s jsonb; d jsonb; ep uuid; run_id uuid; art uuid;
  pay uuid; reg uuid; snap bigint; rec uuid; existing record; idx integer;
begin
  if jsonb_typeof(p) is distinct from 'object' or not coalesce(p ? 'refresh',false)
    then raise exception 'Pharmacy refresh required'; end if;
  if octet_length(p::text)>4194304 or jsonb_array_length(p->'snapshots')<>1
    or jsonb_array_length(p->'artifacts')<>2 then raise exception 'Pharmacy refresh limits'; end if;
  perform pg_advisory_xact_lock(hashtext('fns-pharmacy-import-v1'));
  if p->>'version'<>'fns-pharmacy-import/1.0.0' or p->>'publication_allowed'<>'false'
    or jsonb_array_length(p->'snapshots') not between 1 and 20 then
    raise exception 'Invalid pharmacy import plan';
  end if;
  if p ? 'refresh' then
    if jsonb_typeof(p->'refresh') is distinct from 'object' then
      raise exception 'Invalid pharmacy refresh plan'; end if;
    if (select count(*) from jsonb_object_keys(p->'refresh'))<>jsonb_array_length(p->'snapshots')
      or exists(select 1 from jsonb_array_elements(p->'snapshots') x
        where coalesce(p->'refresh'->>(x->>'scope_key'),'') !~ '^[1-9][0-9]{0,17}$')
    then raise exception 'Invalid pharmacy refresh baseline'; end if;
    lock table source.fns_pharmacy_snapshots,source.fns_pharmacy_decisions in share row exclusive mode;
  end if;
  for a in select value from jsonb_array_elements(p->'artifacts') loop
    select e.id into strict ep from source.source_endpoints e join source.data_sources ds on ds.id=e.data_source_id
      where ds.slug='fns-farmacia-popular' and e.slug=a->>'endpoint' and e.enabled;
    insert into source.collection_runs(source_endpoint_id,idempotency_key,collector_version,parser_version,
      status,attempt_count,started_at,completed_at,metrics)
      values(ep,'pharmacy-import:'||(p->>'plan_sha256')||':'||(a->>'endpoint'),p->>'version',p->>'version',
        'partial',1,clock_timestamp(),clock_timestamp(),'{"publication_allowed":false,"coverage":"partial","mode":"preserved-import"}')
      on conflict(idempotency_key) do nothing;
    select id into strict run_id from source.collection_runs where idempotency_key=
      'pharmacy-import:'||(p->>'plan_sha256')||':'||(a->>'endpoint');
    select * into existing from raw.raw_artifacts where object_key=a->>'object_key';
    if found then
      if existing.sha256<>a->>'sha256' or existing.byte_size<>(a->>'byte_size')::bigint
        or existing.source_endpoint_id<>ep or existing.source_url<>a->>'source_url' then
        raise exception 'Pharmacy artifact replay conflict';
      end if;
    else
      insert into raw.raw_artifacts(collection_run_id,source_endpoint_id,idempotency_key,artifact_kind,
        source_url,retrieved_at,http_status,content_type,byte_size,sha256,object_key,collector_version,parser_version)
      values(run_id,ep,'pharmacy-artifact:'||(a->>'sha256'),
        case when a->>'endpoint' in ('register','register-renewal') then 'document' else 'http_response' end,
        a->>'source_url',(a->>'retrieved_at')::timestamptz,(a->>'http_status')::smallint,
        a->>'content_type',(a->>'byte_size')::bigint,a->>'sha256',a->>'object_key',p->>'version',p->>'version');
    end if;
  end loop;
  for s in select value from jsonb_array_elements(p->'snapshots') loop
    select id into strict pay from raw.raw_artifacts where idempotency_key='pharmacy-artifact:'||(s->>'payment_sha256');
    select id into strict reg from raw.raw_artifacts where idempotency_key='pharmacy-artifact:'||(s->>'register_sha256');
    snap:=null;
    select id into snap from source.fns_pharmacy_snapshots where scope_key=s->>'scope_key'
      and payment_year=(s->>'payment_year')::integer and payment_sha256=s->>'payment_sha256'
      and register_sha256=s->>'register_sha256' order by id desc limit 1;
    if snap is not null then
      if (select count(*) from source.fns_pharmacy_documents where snapshot_id=snap)<>jsonb_array_length(s->'documents')
        or exists(select 1 from jsonb_array_elements(s->'documents') item
          where not exists(select 1 from source.fns_pharmacy_documents pd join raw.raw_records rr on rr.id=pd.raw_record_id
            where pd.snapshot_id=snap and pd.document_key=item->'payload'->>'document_key'
              and rr.payload=item->'payload' and rr.payload_sha256=item->>'payload_sha256'
              and source.pharmacy_document_matches(pd))) then
        raise exception 'Pharmacy snapshot replay conflict';
      end if;
      if p ? 'refresh' then
        perform source.approve_pharmacy_refresh((p->'refresh'->>(s->>'scope_key'))::bigint,snap);
      end if;
      continue;
    end if;
    insert into source.fns_pharmacy_snapshots(scope_key,payment_year,payment_artifact_id,register_artifact_id,
      payment_sha256,register_sha256,establishment,expected_documents)
      values(s->>'scope_key',(s->>'payment_year')::integer,pay,reg,s->>'payment_sha256',s->>'register_sha256',
        s->>'establishment',jsonb_array_length(s->'documents')) returning id into snap;
    for d in select value from jsonb_array_elements(s->'documents') loop
      rec:=null;
      select id into rec from raw.raw_records where idempotency_key=d->>'idempotency_key';
      if rec is null then
        select coalesce(max(record_index)+1,0) into idx from raw.raw_records where raw_artifact_id=pay;
        insert into raw.raw_records(raw_artifact_id,source_record_key,record_type,record_index,payload,
          payload_sha256,parser_version,idempotency_key,collected_at)
          select pay,d->'payload'->>'document_key','fns_pharmacy_payment',idx,d->'payload',
            d->>'payload_sha256',p->>'version',d->>'idempotency_key',retrieved_at
          from raw.raw_artifacts where id=pay returning id into rec;
      end if;
      insert into source.fns_pharmacy_documents(snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row,register_page)
      values(snap,d->'payload'->>'document_key',rec,(d->'payload'->>'document_date')::date,
        (d->'payload'->>'net')::numeric,(d->'payload'->>'source_row')::integer,(d->'payload'->>'register_row')::integer,
        (d->'payload'->>'register_page')::integer);
    end loop;
    if p ? 'refresh' then
      perform source.approve_pharmacy_refresh((p->'refresh'->>(s->>'scope_key'))::bigint,snap);
    end if;
  end loop;
  update source.collection_runs set status='partial',completed_at=clock_timestamp(),
    metrics=metrics||jsonb_build_object('import_verified',true,'publication_allowed',false)
    where idempotency_key in ('pharmacy-import:'||(p->>'plan_sha256')||':payment',
      'pharmacy-import:'||(p->>'plan_sha256')||':register',
      'pharmacy-import:'||(p->>'plan_sha256')||':register-renewal');
end;
$worker$;
create function source.get_pharmacy_refresh_baseline(p_scope text,p_year integer)
returns table(id bigint,approved boolean,payment jsonb,register jsonb)
language sql stable security definer set search_path='' as $$
  select s.id, coalesce((select d.decision='approved'
      from source.fns_pharmacy_decisions d where d.snapshot_id=s.id
      order by d.id desc limit 1),false),
    jsonb_build_object('object_key',p.object_key,'sha256',p.sha256,'byte_size',p.byte_size,
      'source_url',p.source_url,'http_status',p.http_status,'retrieved_at',p.retrieved_at,
      'content_type',p.content_type),
    jsonb_build_object('object_key',r.object_key,'sha256',r.sha256,'byte_size',r.byte_size,
      'source_url',r.source_url,'http_status',r.http_status,'retrieved_at',r.retrieved_at,
      'content_type',r.content_type)
  from source.fns_pharmacy_snapshots s
  join raw.raw_artifacts p on p.id=s.payment_artifact_id
  join raw.raw_artifacts r on r.id=s.register_artifact_id
  where s.scope_key=p_scope and s.payment_year=p_year
  order by s.id desc limit 1;
$$;
create function source.get_pharmacy_refresh_scopes(p_year integer)
returns table(scope_key text) language sql stable security definer set search_path='' as $$
  select distinct s.scope_key from source.fns_pharmacy_snapshots s
  where s.payment_year=p_year order by s.scope_key limit 1001;
$$;
create function source.get_pharmacy_refresh_rows(p_year integer,p_payment text,p_register text)
returns table(id text,establishment text,date date,amount text,sha256 text,register_sha256 text)
language sql stable security definer set search_path='' as $$
  select r.id,r.establishment,r.date,r.amount,r.sha256,r.register_sha256
  from source.reviewed_pharmacy_rows(p_year) r
  where r.sha256=p_payment and r.register_sha256=p_register order by r.id limit 26;
$$;
revoke all on function source.import_pharmacy_refresh(jsonb),
  source.get_pharmacy_refresh_baseline(text,integer),source.get_pharmacy_refresh_scopes(integer),
  source.get_pharmacy_refresh_rows(integer,text,text) from public,anon,authenticated,service_role;
grant usage on schema source to collector_worker;
grant execute on function source.import_pharmacy_refresh(jsonb),
  source.get_pharmacy_refresh_baseline(text,integer),source.get_pharmacy_refresh_scopes(integer),
  source.get_pharmacy_refresh_rows(integer,text,text) to collector_worker;
commit;

