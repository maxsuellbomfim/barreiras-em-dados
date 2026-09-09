begin;
-- Public, read-only allowlist. Never expose run IDs, errors, cursors or raw metrics.
create function api.get_public_pharmacy_refresh(p_year integer)
returns table(year integer,status text,last_attempt_at timestamptz,
  completed_at timestamptz,last_verified_at timestamptz,
  verified_documents integer,pending_scopes integer,missing_scopes integer)
language plpgsql stable security definer set search_path='' as $$
begin
  if p_year is null or p_year not between 2021 and 2100 then
    raise exception 'Invalid pharmacy refresh scope' using errcode='22023'; end if;
  return query
  with runs as (
    select r.* from source.collection_runs r
    join source.source_endpoints e on e.id=r.source_endpoint_id
    join source.data_sources s on s.id=e.data_source_id
    where s.slug='fns-farmacia-popular' and e.slug='payment'
      and r.collector_version='pharmacy-refresh/1.0.0'
      and r.collection_window_start=make_date(p_year,1,1)
      and r.collection_window_end=make_date(p_year,12,31)
      and r.metrics->>'control_plane'='true'
  ), checked as (
    select r.*,case
      when r.status='running' then 'running'
      when r.status='failed' then 'failed'
      when r.completed_at>=r.started_at
        and ((r.status='succeeded' and r.metrics->>'collection_outcome' in ('complete','empty'))
          or (r.status='partial' and r.metrics->>'collection_outcome'='partial'))
        and r.metrics->>'status'=r.metrics->>'collection_outcome'
        and r.metrics->>'verified_documents' ~ '^(0|[1-9][0-9]{0,6})$'
        and r.metrics->>'pending_scopes' ~ '^(0|[1-9][0-9]{0,6})$'
        and r.metrics->>'missing_scopes' ~ '^(0|[1-9][0-9]{0,6})$'
        and (r.metrics->>'collection_outcome'='partial'
          or (r.metrics->>'pending_scopes'='0' and r.metrics->>'missing_scopes'='0'))
        and (r.metrics->>'collection_outcome'<>'empty' or r.metrics->>'verified_documents'='0')
      then r.metrics->>'collection_outcome'
      else 'unavailable' end kind
    from runs r
  ), latest as (
    select * from checked order by started_at desc,id desc limit 1
  )
  select p_year,coalesce(l.kind,'not_started'),l.started_at,l.completed_at,
    (select max(c.completed_at) from checked c where c.kind in ('complete','partial')
      and case when c.kind in ('complete','partial') then (c.metrics->>'verified_documents')::integer>0 else false end),
    case when l.kind in ('complete','partial','empty') then (l.metrics->>'verified_documents')::integer end,
    case when l.kind in ('complete','partial','empty') then (l.metrics->>'pending_scopes')::integer end,
    case when l.kind in ('complete','partial','empty') then (l.metrics->>'missing_scopes')::integer end
  from (values(1)) anchor(n) left join latest l on true;
end;
$$;
revoke all on function api.get_public_pharmacy_refresh(integer)
  from public,anon,authenticated,service_role;
grant usage on schema api to anon,authenticated;
grant execute on function api.get_public_pharmacy_refresh(integer) to anon,authenticated;
comment on function api.get_public_pharmacy_refresh(integer) is
 'Read-only update health: explicit fields only; never annual completeness, raw evidence or worker authority.';
notify pgrst,'reload schema';
commit;
