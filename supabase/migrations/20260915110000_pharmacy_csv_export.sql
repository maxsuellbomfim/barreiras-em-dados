begin;

-- One envelope avoids PostgREST row pagination truncating a complete download.
-- The existing helper validates the whole reviewed year before selecting a scope;
-- materializing it once keeps metadata and records on the same evidence snapshot.
create function api.get_public_pharmacy_export(
  p_year integer, p_establishment_id text default null)
returns table(year integer, filter_applied boolean, selected_establishment text,
  published_documents integer, establishments integer, status text, records jsonb)
language plpgsql stable security definer set search_path='' as $$
begin
  with selected as materialized (
    select r.* from source.filtered_pharmacy_rows(p_year,p_establishment_id) r
    order by r.date desc,r.id limit 5001
  )
  select count(*)::integer,count(distinct r.scope_key)::integer,
    case when p_establishment_id is not null then max(r.establishment) else null end,
    coalesce(jsonb_agg(jsonb_build_object(
      'id',r.id,
      'establishment',r.establishment,
      'date',r.date,
      'amount',r.amount,
      'sha256',r.sha256,
      'register_sha256',r.register_sha256,
      'reviewed_at',r.reviewed_at,
      'historical_registration_verified',r.historical_registration_verified
    ) order by r.date desc,r.id),'[]'::jsonb)
    into published_documents,establishments,selected_establishment,records
    from selected r;

  -- Never label a truncated candidate set as an export. Raise before emitting
  -- the sole envelope, including its counts, so callers cannot receive a part.
  if published_documents>5000 then
    raise exception 'Pharmacy export exceeds 5000 records' using errcode='54000';
  end if;
  year:=p_year;
  filter_applied:=p_establishment_id is not null;
  status:=case when published_documents>0 then 'partial' else 'pending' end;
  return next;
end;
$$;

revoke all on function api.get_public_pharmacy_export(integer,text)
  from public,anon,authenticated,service_role;
grant execute on function api.get_public_pharmacy_export(integer,text)
  to anon,authenticated;

comment on function api.get_public_pharmacy_export(integer,text) is
  'One complete envelope of up to 5000 currently reviewed public payments for one year and optional establishment. Larger selections fail without partial results. Shares the annual evidence gate; partial is not complete annual coverage and pending is not an official zero. No private scope keys or source payloads.';

notify pgrst,'reload schema';
commit;
