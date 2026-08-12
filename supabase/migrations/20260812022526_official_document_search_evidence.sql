-- Registra buscas completas no catálogo oficial. Uma lacuna somente é
-- publicável quando todas as respostas usadas na busca foram preservadas.

create table source.official_document_searches (
  id uuid primary key default gen_random_uuid(),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  resource text not null check (resource ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  period_start date not null,
  period_end date not null,
  search_status text not null check (search_status in ('found', 'not_found')),
  match_count integer not null check (match_count >= 0),
  evidence_manifest_sha256 char(64) not null
    check (evidence_manifest_sha256 ~ '^[0-9a-f]{64}$'),
  evidence_artifact_count integer not null check (evidence_artifact_count > 0),
  checked_at timestamptz not null,
  methodology_version text not null check (length(btrim(methodology_version)) > 0),
  created_at timestamptz not null default statement_timestamp(),
  unique (source_endpoint_id, resource, period_start, evidence_manifest_sha256),
  check (period_start <= period_end),
  check (
    (search_status = 'found' and match_count > 0)
    or (search_status = 'not_found' and match_count = 0)
  )
);

create table source.official_document_search_artifacts (
  official_document_search_id uuid not null
    references source.official_document_searches(id),
  raw_artifact_id uuid not null references raw.raw_artifacts(id),
  artifact_order integer not null check (artifact_order > 0),
  created_at timestamptz not null default statement_timestamp(),
  primary key (official_document_search_id, raw_artifact_id),
  unique (official_document_search_id, artifact_order)
);

create function source.verify_official_document_search_evidence()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  linked_count integer;
  computed_manifest text;
begin
  select
    count(*)::integer,
    encode(
      public.digest(
        string_agg(
          link.raw_artifact_id::text || ':' || artifact.sha256,
          E'\n' order by link.artifact_order
        ),
        'sha256'
      ),
      'hex'
    )
  into linked_count, computed_manifest
  from source.official_document_search_artifacts as link
  join raw.raw_artifacts as artifact
    on artifact.id = link.raw_artifact_id
   and artifact.artifact_kind = 'http_response'
  where link.official_document_search_id = new.id;

  if linked_count <> new.evidence_artifact_count
     or computed_manifest is distinct from new.evidence_manifest_sha256::text then
    raise exception 'official document search evidence manifest mismatch'
      using errcode = '23514';
  end if;
  return null;
end;
$function$;

create index official_document_searches_period_idx
  on source.official_document_searches (
    source_endpoint_id, resource, period_start, checked_at desc
  );
create index official_document_search_artifacts_raw_idx
  on source.official_document_search_artifacts (raw_artifact_id);

alter table source.official_document_searches enable row level security;
alter table source.official_document_searches force row level security;
alter table source.official_document_search_artifacts enable row level security;
alter table source.official_document_search_artifacts force row level security;

revoke all on table source.official_document_searches,
  source.official_document_search_artifacts from public, anon, authenticated;
grant select, insert on table source.official_document_searches,
  source.official_document_search_artifacts to collector_worker;

create policy collector_worker_official_document_searches_select
on source.official_document_searches for select to collector_worker using (true);
create policy collector_worker_official_document_searches_insert
on source.official_document_searches for insert to collector_worker with check (true);
create policy collector_worker_official_document_search_artifacts_select
on source.official_document_search_artifacts for select to collector_worker using (true);
create policy collector_worker_official_document_search_artifacts_insert
on source.official_document_search_artifacts for insert to collector_worker with check (true);

create trigger reject_official_document_search_mutation
before update or delete on source.official_document_searches
for each row execute function audit.reject_mutation();
create trigger reject_official_document_search_artifact_mutation
before update or delete on source.official_document_search_artifacts
for each row execute function audit.reject_mutation();
create constraint trigger verify_official_document_search_evidence
after insert on source.official_document_searches
deferrable initially deferred
for each row execute function source.verify_official_document_search_evidence();

comment on table source.official_document_searches is
  'Resultado mensal append-only de uma busca completa no catálogo oficial; ausência não significa valor zero.';

drop function if exists api.get_public_obligation_coverage(integer, smallint, smallint);

create function api.get_public_obligation_coverage(
  page_size integer default 120,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  coverage_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  coverage_status text,
  source_url text,
  document_artifact_sha256 text,
  search_evidence_sha256 text,
  evidence_artifact_count integer,
  checked_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if page_size < 1 or page_size > 240 then
    raise exception 'page_size deve estar entre 1 e 240' using errcode = '22023';
  end if;
  if fiscal_year_from < 2021
     or effective_year_to < fiscal_year_from
     or effective_year_to > extract(year from current_date)::smallint + 1 then
    raise exception 'intervalo fiscal invalido' using errcode = '22023';
  end if;

  return query
  with expected_months as (
    select month_start::date as period_start
    from generate_series(
      make_date(fiscal_year_from, 1, 1),
      least(
        make_date(effective_year_to, 12, 1),
        date_trunc('month', current_date)::date
      ),
      interval '1 month'
    ) as month_start
  ),
  published_candidates as (
    select
      obligation.fiscal_year, obligation.period_start, obligation.period_end,
      document.source_url, document.sha256,
      coalesce(obligation.validated_at, document.retrieved_at) as checked_at,
      row_number() over (
        partition by obligation.fiscal_year, obligation.period_start
        order by obligation.version desc, obligation.validated_at desc nulls last,
          obligation.created_at desc, obligation.id desc
      ) as priority
    from finance.public_obligations as obligation
    join raw.raw_artifacts as document
      on document.id = obligation.source_document_artifact_id
    where obligation.obligation_type = 'restos_a_pagar_total'
      and obligation.validation_state in ('validated', 'reconciled')
      and finance.has_exact_document_lineage(
        obligation.origin_raw_record_id,
        obligation.source_document_artifact_id
      )
      and not exists (
        select 1 from finance.public_obligations as successor
        where successor.supersedes_id = obligation.id
          and successor.validation_state <> 'rejected'
      )
  ),
  published as (select * from published_candidates where priority = 1),
  terminal_parsed as (
    select
      case when result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
        then (result.result_payload ->> 'fiscal_year')::smallint end as fiscal_year,
      case when result.result_payload ->> 'reference_month' ~ '^([1-9]|1[0-2])$'
        then (result.result_payload ->> 'reference_month')::smallint end
        as reference_month,
      result.candidate_type, document.source_url, document.sha256,
      greatest(result.created_at, job.updated_at) as checked_at,
      result.created_at, result.id
    from raw.extraction_results as result
    join raw.extraction_jobs as job
      on job.id = result.extraction_job_id and job.status = 'succeeded'
    join raw.raw_artifacts as document
      on document.id = job.raw_artifact_id and document.artifact_kind = 'document'
    where result.validation_status = 'valid'
      and (
        (result.candidate_type = 'public_obligation_section_absent'
          and result.result_payload ->> 'classification' = 'absent_in_source_document')
        or
        (result.candidate_type = 'public_obligation_section_incomplete'
          and result.result_payload ->> 'classification' = 'incomplete_in_source_document')
      )
      and document.source_url like 'https://%'
      and document.sha256 ~ '^[0-9a-f]{64}$'
  ),
  terminal_candidates as (
    select terminal_parsed.*,
      row_number() over (
        partition by terminal_parsed.fiscal_year, terminal_parsed.reference_month
        order by terminal_parsed.created_at desc, terminal_parsed.id desc
      ) as priority
    from terminal_parsed
    where terminal_parsed.fiscal_year is not null
      and terminal_parsed.reference_month is not null
  ),
  terminal as (select * from terminal_candidates where priority = 1),
  searches as (
    select distinct on (search.period_start)
      search.period_start, search.search_status, search.evidence_manifest_sha256,
      search.evidence_artifact_count, search.checked_at,
      evidence.source_url
    from source.official_document_searches as search
    join source.source_endpoints as endpoint
      on endpoint.id = search.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    join source.official_document_search_artifacts as link
      on link.official_document_search_id = search.id
     and link.artifact_order = 1
    join raw.raw_artifacts as evidence on evidence.id = link.raw_artifact_id
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and search.resource = 'balancetes'
    order by search.period_start, search.checked_at desc, search.id desc
  )
  select
    format('public-obligation-coverage:%s', to_char(months.period_start, 'YYYY-MM')),
    extract(year from months.period_start)::smallint,
    months.period_start,
    (months.period_start + interval '1 month - 1 day')::date,
    case
      when published.period_start is not null then 'published'
      when terminal.candidate_type = 'public_obligation_section_absent'
        then 'section_absent'
      when terminal.candidate_type = 'public_obligation_section_incomplete'
        then 'section_incomplete'
      when searches.search_status = 'not_found' then 'document_not_found'
      else 'document_not_confirmed'
    end,
    coalesce(published.source_url, terminal.source_url, searches.source_url),
    coalesce(published.sha256, terminal.sha256),
    searches.evidence_manifest_sha256::text,
    searches.evidence_artifact_count,
    coalesce(published.checked_at, terminal.checked_at, searches.checked_at),
    'public-obligation-coverage/1.1.0'::text
  from expected_months as months
  left join published on published.period_start = months.period_start
  left join terminal
    on terminal.fiscal_year = extract(year from months.period_start)::smallint
   and terminal.reference_month = extract(month from months.period_start)::smallint
  left join searches on searches.period_start = months.period_start
  order by months.period_start desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_obligation_coverage(integer, smallint, smallint)
  from public;
grant execute on function api.get_public_obligation_coverage(integer, smallint, smallint)
  to anon, authenticated;

comment on function api.get_public_obligation_coverage(integer, smallint, smallint) is
  'Cobertura mensal com busca oficial preservada: ausencia nunca e valor zero nem prova de omissao permanente.';
