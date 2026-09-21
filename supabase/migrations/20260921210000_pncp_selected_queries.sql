begin;
set local lock_timeout='3s';
set local statement_timeout='30s';
create or replace function source.refresh_pncp_contract_query_status(target_run uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
  r source.collection_runs%rowtype;
  controls jsonb; observations jsonb; item jsonb; page jsonb; artifact raw.raw_artifacts%rowtype;
  key text; result_state text; checked timestamptz; started timestamptz;
  evidence jsonb; page_count integer; row_count bigint; position integer;
begin
  select run.* into r from source.collection_runs run
  join source.source_endpoints e on e.id=run.source_endpoint_id
  join source.data_sources s on s.id=e.data_source_id
  where run.id=target_run and s.slug='pncp' and e.slug='contratos-api'
    and run.metrics->'control_plane'='true'::jsonb;
  if not found or r.started_at is null then return; end if;
  observations := case when jsonb_typeof(r.metrics->'control_observations')='array'
    then r.metrics->'control_observations' else '[]'::jsonb end;
  if jsonb_array_length(observations)>50 then observations := '[]'::jsonb; end if;
  controls := case when r.cursor_after->'cursor_version'='1'::jsonb
    and jsonb_typeof(r.cursor_after->'retry_controls')='array'
    then r.cursor_after->'retry_controls' else '[]'::jsonb end;
  -- Only explicit selections are new reservations. Legacy cursors remain conservative.
  if r.cursor_after ? 'selected_query_controls'
    and jsonb_typeof(r.cursor_after->'selected_query_controls')='array'
    and jsonb_array_length(r.cursor_after->'selected_query_controls')<=50
  then
    controls := r.cursor_after->'selected_query_controls';
  end if;
  for key in
    select distinct candidate from (
      select value #>> '{}' as candidate from jsonb_array_elements(controls)
      union all select value->>'control' from jsonb_array_elements(observations)
    ) q where candidate ~ '^13654405000195-1-[0-9]{1,12}/[0-9]{4}$'
  loop
    result_state := 'pending'; checked := null; evidence := '[]'::jsonb;
    if r.completed_at is not null and r.status in ('succeeded','partial') then
      select value into item from jsonb_array_elements(observations)
        where value->>'control'=key limit 1;
      if found then
        result_state := 'unknown';
        begin
          if (select count(*) from jsonb_array_elements(observations) where value->>'control'=key)<>1
            or item->'version' is distinct from '1'::jsonb
            or item->>'scope' is distinct from 'pncp_contracts_query'
            or coalesce(item->>'state','') not in ('query_complete','empty_confirmed','inconclusive','partial','interrupted','awaiting_source_publication')
            or jsonb_typeof(item->'pages') is distinct from 'array'
            or item->>'started_at' is null or item->>'finished_at' is null
          then raise exception using errcode='22023', message='Invalid observation'; end if;
          started := (item->>'started_at')::timestamptz;
          checked := (item->>'finished_at')::timestamptz;
          if started<r.started_at or checked<started or checked>r.completed_at then
            raise exception using errcode='22023', message='Invalid observation dates'; end if;
          page_count := jsonb_array_length(item->'pages'); row_count := 0; position := 0;
          if page_count>30 then raise exception using errcode='22023', message='Invalid page limit'; end if;
          for page in select value from jsonb_array_elements(item->'pages') loop
            position := position+1;
            if page->'page' is distinct from to_jsonb(position)
              or page->'http_status' is distinct from '200'::jsonb
              or coalesce(page->>'records','') !~ '^(0|[1-9][0-9]{0,4})$'
              or jsonb_typeof(page->'records') is distinct from 'number'
              or coalesce(page->>'sha256','') !~ '^[0-9a-f]{64}$'
            then raise exception using errcode='22023', message='Invalid page evidence'; end if;
            select * into artifact from raw.raw_artifacts where id=(page->>'raw_artifact_id')::uuid;
            if not found or artifact.sha256 is distinct from page->>'sha256'
              or artifact.http_status is distinct from 200
              or artifact.metadata->>'schema_name' is distinct from 'pncp-contratos-page'
              or (artifact.metadata->'cursor'->>'pagina')::bigint is distinct from position::bigint
              or (artifact.metadata->'cursor'->>'ano')::bigint is distinct from split_part(key,'/',2)::bigint
              or (artifact.metadata->'cursor'->>'sequencial')::bigint is distinct from split_part(split_part(key,'-',3),'/',1)::bigint
            then raise exception using errcode='22023', message='Incompatible artifact'; end if;
            row_count := row_count+(page->>'records')::bigint;
          end loop;
          if (page_count=0 and item->'records_preserved' is distinct from 'null'::jsonb)
            or (page_count>0 and item->'records_preserved' is distinct from to_jsonb(row_count))
            or (item->>'state' in ('query_complete','empty_confirmed') and page_count=0)
            or (item->>'state'='empty_confirmed' and row_count<>0)
            or (item->>'state'='query_complete' and row_count=0)
          then raise exception using errcode='22023', message='Invalid observation count'; end if;
          if item->>'state'='awaiting_source_publication' then
            page := item->'response_evidence';
            if page_count<>0
              or item->>'reason' is distinct from 'source_reports_no_published_contract'
              or item->'http_status' is distinct from '404'::jsonb
              or item->'response_page' is distinct from '1'::jsonb
              or page->'http_status' is distinct from '404'::jsonb
              or coalesce(page->>'sha256','') !~ '^[0-9a-f]{64}$'
            then raise exception using errcode='22023', message='Invalid private response'; end if;
            select * into artifact from raw.raw_artifacts
              where id=(page->>'raw_artifact_id')::uuid;
            if not found or artifact.sha256 is distinct from page->>'sha256'
              or artifact.http_status is distinct from 404
              or artifact.metadata->>'schema_name' is distinct from 'pncp-registry-snapshot'
              or artifact.metadata->>'resource' is distinct from
                ('contract-response:/api/pncp/v1/orgaos/13654405000195/contratos/contratacao/'
                 ||split_part(key,'/',2)||'/'
                 ||split_part(split_part(key,'-',3),'/',1)::bigint::text)
            then raise exception using errcode='22023', message='Incompatible private response'; end if;
            evidence := jsonb_build_array(page);
          else
            evidence := item->'pages';
          end if;
          result_state := item->>'state';
        exception when data_exception then
          result_state := 'unknown'; checked := null; evidence := '[]'::jsonb;
        end;
      end if;
    end if;
    insert into source.pncp_contract_query_status as current
      (control_number,run_id,run_started_at,state,checked_at,evidence)
    values (key,r.id,r.started_at,result_state,checked,evidence)
    on conflict (control_number) do update set
      run_id=excluded.run_id,run_started_at=excluded.run_started_at,state=excluded.state,
      checked_at=excluded.checked_at,evidence=excluded.evidence,updated_at=statement_timestamp()
    where (excluded.run_started_at,excluded.run_id)>=(current.run_started_at,current.run_id);
  end loop;
end $$;
revoke all on function source.refresh_pncp_contract_query_status(uuid) from public, anon, authenticated, collector_worker;



-- Historical cursors lack explicit selection; do not infer it retroactively.
commit;

