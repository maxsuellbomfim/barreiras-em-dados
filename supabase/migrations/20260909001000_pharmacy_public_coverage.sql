begin;

-- One gate for both page rows and counts: no independent, stale totals.
create function source.reviewed_pharmacy_rows(p_year integer)
returns table(id text, establishment text, date date, amount text, sha256 text,
  register_sha256 text, reviewed_at timestamptz, historical_registration_verified boolean,
  scope_key text)
language sql stable security definer set search_path='' as $$
  with latest as materialized (
    select distinct on(s.scope_key) s.* from source.fns_pharmacy_snapshots s
    where s.payment_year=p_year order by s.scope_key,s.id desc
  ), documents as materialized (
    select d.*,source.pharmacy_document_matches(d) evidence_matches,
      count(*) over(partition by d.document_key) multiplicity
    from source.fns_pharmacy_documents d join latest s on s.id=d.snapshot_id
  )
  select d.document_key,s.establishment,d.document_date,d.net_amount::text,
    s.payment_sha256,s.register_sha256,v.decided_at,false,s.scope_key
  from latest s join documents d on d.snapshot_id=s.id
  join lateral (select z.decision,z.decided_at from source.fns_pharmacy_decisions z
    where z.snapshot_id=s.id order by z.id desc limit 1) v on v.decision='approved'
  where d.multiplicity=1
    and s.expected_documents=(select count(*) from documents a where a.snapshot_id=s.id)
    and not exists(select 1 from documents a where a.snapshot_id=s.id
      and (a.multiplicity<>1 or not a.evidence_matches));
$$;
revoke all on function source.reviewed_pharmacy_rows(integer)
  from public,anon,authenticated,service_role;

create or replace function api.get_public_pharmacy_payments(p_year integer, p_offset integer default 0)
returns table(id text, establishment text, date date, amount text, sha256 text,
  register_sha256 text, reviewed_at timestamptz, historical_registration_verified boolean)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_year is null or p_year not between 2021 and 2100
    or p_offset is null or p_offset not between 0 and 10000 then
    raise exception 'Invalid pharmacy page scope' using errcode='22023';
  end if;
  return query select r.id,r.establishment,r.date,r.amount,r.sha256,
    r.register_sha256,r.reviewed_at,r.historical_registration_verified
    from source.reviewed_pharmacy_rows(p_year) r
    order by r.date desc,r.id limit 25 offset p_offset;
end;
$$;

create function api.get_public_pharmacy_coverage(p_year integer)
returns table(year integer, published_documents integer, establishments integer,
  first_date date, last_date date, status text)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_year is null or p_year not between 2021 and 2100 then
    raise exception 'Invalid pharmacy coverage scope' using errcode='22023';
  end if;
  return query select p_year,count(*)::integer,count(distinct r.scope_key)::integer,
    min(r.date),max(r.date),case when count(*)>0 then 'partial' else 'pending' end
    from source.reviewed_pharmacy_rows(p_year) r;
end;
$$;
revoke all on function api.get_public_pharmacy_coverage(integer)
  from public,anon,authenticated,service_role;
grant execute on function api.get_public_pharmacy_coverage(integer) to anon,authenticated;
comment on function api.get_public_pharmacy_coverage(integer) is
  'Current reviewed publication counts, not source totals or annual completeness. Pending never means official zero.';
notify pgrst,'reload schema';
commit;
