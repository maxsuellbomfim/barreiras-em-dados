-- Explica publicamente por que um mês não possui valor publicado.
-- A projeção nunca transforma ausência de documento ou seção em zero e
-- não expõe detalhes internos de OCR, parser ou mensagens de erro.

create or replace function api.get_public_obligation_coverage(
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
    raise exception 'page_size deve estar entre 1 e 240'
      using errcode = '22023';
  end if;

  if fiscal_year_from < 2021
     or effective_year_to < fiscal_year_from
     or effective_year_to > extract(year from current_date)::smallint + 1 then
    raise exception 'intervalo fiscal invalido'
      using errcode = '22023';
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
        select 1
        from finance.public_obligations as successor
        where successor.supersedes_id = obligation.id
          and successor.validation_state <> 'rejected'
      )
  ),
  published as (
    select *
    from published_candidates
    where priority = 1
  ),
  terminal_parsed as (
    select
      case
        when result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
          then (result.result_payload ->> 'fiscal_year')::smallint
      end as fiscal_year,
      case
        when result.result_payload ->> 'reference_month' ~ '^([1-9]|1[0-2])$'
          then (result.result_payload ->> 'reference_month')::smallint
      end as reference_month,
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
    select *
    from terminal_candidates
    where priority = 1
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
      when terminal.candidate_type = 'public_obligation_section_absent'
        then 'section_absent'
      when terminal.candidate_type = 'public_obligation_section_incomplete'
        then 'section_incomplete'
      else 'document_not_confirmed'
    end,
    coalesce(published.source_url, terminal.source_url),
    coalesce(published.sha256, terminal.sha256),
    coalesce(published.checked_at, terminal.checked_at),
    'public-obligation-coverage/1.0.0'::text
  from expected_months as months
  left join published
    on published.period_start = months.period_start
  left join terminal
    on terminal.fiscal_year = extract(year from months.period_start)::smallint
   and terminal.reference_month = extract(month from months.period_start)::smallint
  order by months.period_start desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_obligation_coverage(integer, smallint, smallint)
  from public;
grant execute on function api.get_public_obligation_coverage(integer, smallint, smallint)
  to anon, authenticated;

comment on function api.get_public_obligation_coverage(integer, smallint, smallint) is
  'Cobertura mensal de restos a pagar: publicado, secao ausente, fonte incompleta ou documento ainda nao confirmado; ausencia nunca e zero.';
