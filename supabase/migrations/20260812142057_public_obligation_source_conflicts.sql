-- Divergencias entre dois balancetes oficiais consecutivos nao sao falhas de
-- coleta nem valores conciliados. O worker preserva as duas evidencias e a
-- projecao publica explica a diferenca sem expor detalhes internos de revisao.

grant select on evidence.evidence_items to collector_worker;
grant select, insert on evidence.source_conflicts to collector_worker;

create policy collector_worker_evidence_items_select
on evidence.evidence_items
for select to collector_worker
using (true);

create policy collector_worker_source_conflicts_select
on evidence.source_conflicts
for select to collector_worker
using (
  target_type = 'finance.public_obligations'
  and field_name = 'payments_prior_amount'
);

create policy collector_worker_source_conflicts_insert
on evidence.source_conflicts
for insert to collector_worker
with check (
  target_type = 'finance.public_obligations'
  and field_name = 'payments_prior_amount'
  and status = 'open'
);

create unique index source_conflicts_evidence_pair_unique_idx
on evidence.source_conflicts (
  target_type,
  target_id,
  field_name,
  first_evidence_item_id,
  second_evidence_item_id
);

drop function if exists api.get_public_obligation_coverage(
  integer,
  smallint,
  smallint
);

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
  conflict_previous_period_amount numeric(20,2),
  conflict_reported_prior_amount numeric(20,2),
  conflict_difference_amount numeric(20,2),
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
      obligation.fiscal_year,
      obligation.period_start,
      obligation.period_end,
      document.source_url,
      document.sha256,
      coalesce(obligation.validated_at, document.retrieved_at) as checked_at,
      row_number() over (
        partition by obligation.fiscal_year, obligation.period_start
        order by obligation.version desc,
          obligation.validated_at desc nulls last,
          obligation.created_at desc,
          obligation.id desc
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
        select 1
        from finance.public_obligations as successor
        where successor.supersedes_id = obligation.id
          and successor.validation_state <> 'rejected'
      )
  ),
  published as (
    select * from published_candidates where priority = 1
  ),
  conflict_parsed as (
    select
      obligation.fiscal_year,
      obligation.period_start,
      obligation.period_end,
      document.source_url,
      document.sha256,
      greatest(conflict.created_at, document.retrieved_at) as checked_at,
      case
        when conflict.first_value ->> 'payments_to_date_amount'
          ~ '^[0-9]+([.][0-9]{1,2})?$'
          then (conflict.first_value ->> 'payments_to_date_amount')::numeric(20,2)
      end as previous_period_amount,
      case
        when conflict.second_value ->> 'payments_prior_amount'
          ~ '^[0-9]+([.][0-9]{1,2})?$'
          then (conflict.second_value ->> 'payments_prior_amount')::numeric(20,2)
      end as reported_prior_amount,
      conflict.created_at,
      conflict.id
    from finance.public_obligations as obligation
    join evidence.source_conflicts as conflict
      on conflict.target_type = 'finance.public_obligations'
     and conflict.target_id = obligation.id
     and conflict.field_name = 'payments_prior_amount'
     and conflict.status in ('open', 'accepted_difference')
    join raw.raw_artifacts as document
      on document.id = obligation.source_document_artifact_id
    where obligation.obligation_type = 'restos_a_pagar_total'
      and obligation.validation_state = 'conflict'
      and document.source_url like 'https://%'
      and document.sha256 ~ '^[0-9a-f]{64}$'
  ),
  conflict_candidates as (
    select
      conflict_parsed.*,
      row_number() over (
        partition by conflict_parsed.fiscal_year, conflict_parsed.period_start
        order by conflict_parsed.created_at desc, conflict_parsed.id desc
      ) as priority
    from conflict_parsed
    where conflict_parsed.previous_period_amount is not null
      and conflict_parsed.reported_prior_amount is not null
  ),
  conflicts as (
    select * from conflict_candidates where priority = 1
  ),
  terminal_parsed as (
    select
      case when result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
        then (result.result_payload ->> 'fiscal_year')::smallint end as fiscal_year,
      case when result.result_payload ->> 'reference_month' ~ '^([1-9]|1[0-2])$'
        then (result.result_payload ->> 'reference_month')::smallint end
        as reference_month,
      result.candidate_type,
      document.source_url,
      document.sha256,
      greatest(result.created_at, job.updated_at) as checked_at,
      result.created_at,
      result.id
    from raw.extraction_results as result
    join raw.extraction_jobs as job
      on job.id = result.extraction_job_id
     and job.status = 'succeeded'
    join raw.raw_artifacts as document
      on document.id = job.raw_artifact_id
     and document.artifact_kind = 'document'
    where result.validation_status = 'valid'
      and (
        (
          result.candidate_type = 'public_obligation_section_absent'
          and result.result_payload ->> 'classification'
            = 'absent_in_source_document'
        )
        or (
          result.candidate_type = 'public_obligation_section_incomplete'
          and result.result_payload ->> 'classification'
            = 'incomplete_in_source_document'
        )
      )
      and document.source_url like 'https://%'
      and document.sha256 ~ '^[0-9a-f]{64}$'
  ),
  terminal_candidates as (
    select
      terminal_parsed.*,
      row_number() over (
        partition by terminal_parsed.fiscal_year, terminal_parsed.reference_month
        order by terminal_parsed.created_at desc, terminal_parsed.id desc
      ) as priority
    from terminal_parsed
    where terminal_parsed.fiscal_year is not null
      and terminal_parsed.reference_month is not null
  ),
  terminal as (
    select * from terminal_candidates where priority = 1
  ),
  searches as (
    select distinct on (search.period_start)
      search.period_start,
      search.search_status,
      search.evidence_manifest_sha256,
      search.evidence_artifact_count,
      search.checked_at,
      evidence.source_url
    from source.official_document_searches as search
    join source.source_endpoints as endpoint
      on endpoint.id = search.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    join source.official_document_search_artifacts as link
      on link.official_document_search_id = search.id
     and link.artifact_order = 1
    join raw.raw_artifacts as evidence
      on evidence.id = link.raw_artifact_id
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and search.resource = 'balancetes'
    order by search.period_start, search.checked_at desc, search.id desc
  )
  select
    format(
      'public-obligation-coverage:%s',
      to_char(months.period_start, 'YYYY-MM')
    ),
    extract(year from months.period_start)::smallint,
    months.period_start,
    (months.period_start + interval '1 month - 1 day')::date,
    case
      when published.period_start is not null then 'published'
      when conflicts.period_start is not null then 'source_conflict'
      when terminal.candidate_type = 'public_obligation_section_absent'
        then 'section_absent'
      when terminal.candidate_type = 'public_obligation_section_incomplete'
        then 'section_incomplete'
      when searches.search_status = 'not_found' then 'document_not_found'
      else 'document_not_confirmed'
    end,
    coalesce(
      published.source_url,
      conflicts.source_url,
      terminal.source_url,
      searches.source_url
    ),
    coalesce(published.sha256, conflicts.sha256, terminal.sha256),
    searches.evidence_manifest_sha256::text,
    searches.evidence_artifact_count,
    conflicts.previous_period_amount,
    conflicts.reported_prior_amount,
    case
      when conflicts.period_start is not null
        then abs(
          conflicts.previous_period_amount - conflicts.reported_prior_amount
        )
    end,
    coalesce(
      published.checked_at,
      conflicts.checked_at,
      terminal.checked_at,
      searches.checked_at
    ),
    'public-obligation-coverage/1.2.0'::text
  from expected_months as months
  left join published
    on published.period_start = months.period_start
  left join conflicts
    on conflicts.period_start = months.period_start
  left join terminal
    on terminal.fiscal_year = extract(year from months.period_start)::smallint
   and terminal.reference_month = extract(month from months.period_start)::smallint
  left join searches
    on searches.period_start = months.period_start
  order by months.period_start desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_obligation_coverage(
  integer,
  smallint,
  smallint
) from public;
grant execute on function api.get_public_obligation_coverage(
  integer,
  smallint,
  smallint
) to anon, authenticated;

comment on function api.get_public_obligation_coverage(
  integer,
  smallint,
  smallint
) is
  'Cobertura mensal com divergencia oficial explicita; valores conflitantes ficam fora da projecao financeira validada.';
