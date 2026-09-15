begin;

-- Resolve an already-public document reference only within its currently reviewed
-- year. Never publish the private scope key or bypass the year-global evidence gate.
create function source.filtered_pharmacy_rows(p_year integer, p_establishment_id text)
returns table(id text, establishment text, date date, amount text, sha256 text,
  register_sha256 text, reviewed_at timestamptz, historical_registration_verified boolean,
  scope_key text)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_year is null or p_year not between 2021 and 2100 then
    raise exception 'Invalid pharmacy year scope' using errcode='22023';
  end if;
  if p_establishment_id is not null and p_establishment_id !~ '^[0-9a-f]{64}$' then
    raise exception 'Invalid pharmacy establishment selection' using errcode='22023';
  end if;
  return query
    with reviewed as materialized (
      select * from source.reviewed_pharmacy_rows(p_year)
    )
    select r.* from reviewed r
    where p_establishment_id is null or r.scope_key=(
      select anchor.scope_key from reviewed anchor where anchor.id=p_establishment_id
    );
  if p_establishment_id is not null and not found then
    raise exception 'Invalid pharmacy establishment selection' using errcode='22023';
  end if;
end;
$$;
revoke all on function source.filtered_pharmacy_rows(integer,text)
  from public,anon,authenticated,service_role;

create function api.get_public_pharmacy_payments_filtered(
  p_year integer, p_establishment_id text default null, p_offset integer default 0)
returns table(id text, establishment text, date date, amount text, sha256 text,
  register_sha256 text, reviewed_at timestamptz, historical_registration_verified boolean)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_offset is null or p_offset not between 0 and 10000 then
    raise exception 'Invalid pharmacy page scope' using errcode='22023';
  end if;
  return query select r.id,r.establishment,r.date,r.amount,r.sha256,
    r.register_sha256,r.reviewed_at,r.historical_registration_verified
    from source.filtered_pharmacy_rows(p_year,p_establishment_id) r
    order by r.date desc,r.id limit 25 offset p_offset;
end;
$$;

create function api.get_public_pharmacy_coverage_filtered(
  p_year integer, p_establishment_id text default null)
returns table(year integer, published_documents integer, establishments integer,
  first_date date, last_date date, status text, selected_establishment text,
  filter_applied boolean)
language plpgsql stable security definer set search_path='' as $$
begin
  return query select p_year,count(*)::integer,count(distinct r.scope_key)::integer,
    min(r.date),max(r.date),case when count(*)>0 then 'partial' else 'pending' end,
    case when p_establishment_id is not null then max(r.establishment) else null end,
    p_establishment_id is not null
    from source.filtered_pharmacy_rows(p_year,p_establishment_id) r;
end;
$$;

create function api.get_public_pharmacy_establishments(
  p_year integer, p_offset integer default 0)
returns table(establishment_id text, establishment text)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_offset is null or p_offset not between 0 and 10000 then
    raise exception 'Invalid pharmacy establishment page scope' using errcode='22023';
  end if;
  -- Names can be identical across scopes. The minimum reviewed document id is
  -- only the current option reference; any still-reviewed id resolves above.
  return query select min(r.id),min(r.establishment)
    from source.filtered_pharmacy_rows(p_year,null) r
    group by r.scope_key
    order by min(r.establishment),min(r.id) limit 25 offset p_offset;
end;
$$;

revoke all on function api.get_public_pharmacy_payments_filtered(integer,text,integer)
  from public,anon,authenticated,service_role;
revoke all on function api.get_public_pharmacy_coverage_filtered(integer,text)
  from public,anon,authenticated,service_role;
revoke all on function api.get_public_pharmacy_establishments(integer,integer)
  from public,anon,authenticated,service_role;
grant execute on function api.get_public_pharmacy_payments_filtered(integer,text,integer)
  to anon,authenticated;
grant execute on function api.get_public_pharmacy_coverage_filtered(integer,text)
  to anon,authenticated;
grant execute on function api.get_public_pharmacy_establishments(integer,integer)
  to anon,authenticated;

comment on function api.get_public_pharmacy_establishments(integer,integer) is
  'Up to 25 currently reviewed establishment options for one year, not a complete pharmacy registry. Reference reuses an existing public document id, not a private scope key.';
comment on function api.get_public_pharmacy_coverage_filtered(integer,text) is
  'Counts use exactly the payment selection after the global evidence gate. An unknown or no-longer-reviewed selection fails closed; pending is not an official zero.';

notify pgrst,'reload schema';
commit;
