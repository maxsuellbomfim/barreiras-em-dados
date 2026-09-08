begin;

-- Private append-only snapshots. Trusted importer must hash Storage bytes and
-- rerun identity/reconciliation; SQL lineage checks do not replace that work.
create table source.fns_pharmacy_snapshots (
  id bigint generated always as identity primary key,
  scope_key text not null check (scope_key ~ '^[0-9a-f]{64}$'),
  payment_year integer not null check (payment_year between 2021 and 2100),
  payment_artifact_id uuid not null references raw.raw_artifacts(id),
  register_artifact_id uuid not null references raw.raw_artifacts(id),
  payment_sha256 text not null check (payment_sha256 ~ '^[0-9a-f]{64}$'),
  register_sha256 text not null check (register_sha256 ~ '^[0-9a-f]{64}$'),
  establishment text not null check (establishment = btrim(establishment)
    and length(establishment) between 2 and 180
    and establishment !~ '[<>[:cntrl:]]|[0-9]{11}'),
  expected_documents integer not null check (expected_documents between 1 and 25),
  created_at timestamptz not null default clock_timestamp(),
  check (payment_artifact_id <> register_artifact_id)
);
create index fns_pharmacy_latest on source.fns_pharmacy_snapshots(payment_year,scope_key,id desc);

create table source.fns_pharmacy_documents (
  snapshot_id bigint not null references source.fns_pharmacy_snapshots(id),
  document_key text not null check (document_key ~ '^[0-9a-f]{64}$'),
  raw_record_id uuid not null references raw.raw_records(id),
  document_date date not null,
  net_amount numeric(14,2) not null check (net_amount >= 0 and net_amount <> 'NaN'::numeric),
  source_row integer not null check (source_row between 1 and 25),
  register_row integer not null check (register_row between 2 and 1001),
  primary key (snapshot_id,document_key),
  unique(snapshot_id,source_row), unique(snapshot_id,raw_record_id)
);
create index fns_pharmacy_document_key on source.fns_pharmacy_documents(document_key);

create table source.fns_pharmacy_decisions (
  id bigint generated always as identity primary key,
  snapshot_id bigint not null references source.fns_pharmacy_snapshots(id),
  decision text not null check (decision in ('approved','rejected','revoked')),
  reviewer_ref text not null check (reviewer_ref ~ '^[a-zA-Z0-9:_.-]{3,100}$'),
  review_note text not null check (length(btrim(review_note)) between 20 and 2000),
  database_role text not null default current_user,
  decided_at timestamptz not null default clock_timestamp()
);
create index fns_pharmacy_last_decision on source.fns_pharmacy_decisions(snapshot_id,id desc);

alter table source.fns_pharmacy_snapshots enable row level security;
alter table source.fns_pharmacy_documents enable row level security;
alter table source.fns_pharmacy_decisions enable row level security;
revoke all on source.fns_pharmacy_snapshots, source.fns_pharmacy_documents,
  source.fns_pharmacy_decisions from public, anon, authenticated, service_role;
revoke all on sequence source.fns_pharmacy_snapshots_id_seq, source.fns_pharmacy_decisions_id_seq
  from public, anon, authenticated, service_role;
create trigger reject_mutation before update or delete on source.fns_pharmacy_snapshots
  for each row execute function audit.reject_mutation();
create trigger reject_mutation before update or delete on source.fns_pharmacy_documents
  for each row execute function audit.reject_mutation();
create trigger reject_mutation before update or delete on source.fns_pharmacy_decisions
  for each row execute function audit.reject_mutation();

create function source.pharmacy_document_matches(d source.fns_pharmacy_documents)
returns boolean language sql stable security invoker set search_path='' as $$
  select exists (
    select 1 from source.fns_pharmacy_snapshots s
    join raw.raw_artifacts p on p.id=s.payment_artifact_id
    join raw.raw_artifacts x on x.id=s.register_artifact_id
    join raw.raw_records r on r.id=d.raw_record_id and r.raw_artifact_id=p.id
    where s.id=d.snapshot_id
      and p.sha256=s.payment_sha256 and x.sha256=s.register_sha256
      and p.byte_size>0 and x.byte_size>0 and p.http_status=200
      and (x.http_status is null or x.http_status=200)
      and p.content_type='application/json'
      and x.content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      and p.source_url ~ '^https://consultafns[.]saude[.]gov[.]br/recursos/consulta-detalhada/detalhe-pagamento[?]'
      and x.source_url ~ '^https://infoms[.]saude[.]gov[.]br/tempcontent/[^#[:space:]]+[.]xlsx([?][^#[:space:]]*)?$'
      and extract(year from d.document_date)=s.payment_year
      and r.record_type='fns_pharmacy_payment'
      and r.payload->>'document_key'=d.document_key
      and r.payload->>'document_date'=d.document_date::text
      and r.payload->>'net'=d.net_amount::text
      and r.payload->>'source_row'=d.source_row::text
      and r.payload->>'register_row'=d.register_row::text
      and r.payload->>'register_sha256'=s.register_sha256
      and r.payload->>'establishment'=s.establishment
  );
$$;
revoke all on function source.pharmacy_document_matches(source.fns_pharmacy_documents)
  from public, anon, authenticated, service_role;

-- Both inserts lock the parent to serialize document insertion with approval.
create function source.guard_pharmacy_document() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
  perform 1 from source.fns_pharmacy_snapshots s where s.id=new.snapshot_id for update;
  if exists (select 1 from source.fns_pharmacy_decisions v where v.snapshot_id=new.snapshot_id) then
    raise exception 'Pharmacy snapshot is sealed' using errcode='23514';
  end if;
  if not source.pharmacy_document_matches(new) then
    raise exception 'Pharmacy evidence mismatch' using errcode='23514';
  end if;
  return new;
end;
$$;
revoke all on function source.guard_pharmacy_document() from public, anon, authenticated, service_role;
create trigger guard_pharmacy_document before insert on source.fns_pharmacy_documents
  for each row execute function source.guard_pharmacy_document();

create function source.guard_pharmacy_decision() returns trigger
language plpgsql security invoker set search_path='' as $$
declare expected integer;
begin
  select s.expected_documents into expected from source.fns_pharmacy_snapshots s
    where s.id=new.snapshot_id for update;
  if new.decision='approved' and (
    expected is null or expected<>(select count(*) from source.fns_pharmacy_documents d where d.snapshot_id=new.snapshot_id)
    or exists (select 1 from source.fns_pharmacy_documents d where d.snapshot_id=new.snapshot_id
      and not source.pharmacy_document_matches(d))
  ) then
    raise exception 'Pharmacy evidence incomplete or mismatched' using errcode='23514';
  end if;
  return new;
end;
$$;
revoke all on function source.guard_pharmacy_decision() from public, anon, authenticated, service_role;
create trigger guard_pharmacy_decision before insert on source.fns_pharmacy_decisions
  for each row execute function source.guard_pharmacy_decision();

-- Public metadata only. No source URLs with query identifiers, private IDs,
-- bank fields, review notes, annual totals or historical accreditation claim.
create function api.get_public_pharmacy_payments(p_year integer, p_offset integer default 0)
returns table(id text, establishment text, date date, amount text, sha256 text,
  register_sha256 text, reviewed_at timestamptz, historical_registration_verified boolean)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_year is null or p_year not between 2021 and 2100
    or p_offset is null or p_offset not between 0 and 10000 then
    raise exception 'Invalid pharmacy page scope' using errcode='22023';
  end if;
  return query
  with latest as materialized (
    select distinct on(s.scope_key) s.* from source.fns_pharmacy_snapshots s
    where s.payment_year=p_year order by s.scope_key,s.id desc
  ), documents as materialized (
    select d.*,source.pharmacy_document_matches(d) evidence_matches,
      count(*) over(partition by d.document_key) multiplicity
    from source.fns_pharmacy_documents d join latest s on s.id=d.snapshot_id
  )
  select d.document_key,s.establishment,d.document_date,d.net_amount::text,
    s.payment_sha256,s.register_sha256,v.decided_at,false
  from latest s join documents d on d.snapshot_id=s.id
  join lateral (select z.decision,z.decided_at from source.fns_pharmacy_decisions z
    where z.snapshot_id=s.id order by z.id desc limit 1) v on v.decision='approved'
  where d.multiplicity=1
    and s.expected_documents=(select count(*) from documents a where a.snapshot_id=s.id)
    and not exists(select 1 from documents a where a.snapshot_id=s.id
      and (a.multiplicity<>1 or not a.evidence_matches))
  order by d.document_date desc,d.document_key limit 25 offset p_offset;
end;
$$;
revoke all on function api.get_public_pharmacy_payments(integer,integer)
  from public, anon, authenticated, service_role;
grant execute on function api.get_public_pharmacy_payments(integer,integer) to anon,authenticated;

comment on table source.fns_pharmacy_snapshots is
  'Private institutional/year scope hash from trusted importer; latest snapshot blocks fallback. No automatic grants to collectors.';
comment on function api.get_public_pharmacy_payments(integer,integer) is
  'Reviewed FNS establishment payments only; never municipal revenue or amendment rankings. No historical accreditation or annual coverage claim.';
notify pgrst,'reload schema';
commit;
