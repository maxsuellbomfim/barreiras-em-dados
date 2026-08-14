begin;

create function api.get_public_parliamentary_legislature_year_coverage(
  sphere_filter text default null,
  legislature_number_filter smallint default null
)
returns table (
  sphere text,
  legislature_number smallint,
  fiscal_year smallint,
  observation_status text,
  contribution_count integer,
  author_count integer,
  primary_evidence_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if sphere_filter is not null and sphere_filter not in ('federal', 'state') then
    raise exception 'esfera legislativa deve ser federal ou state'
      using errcode = '22023';
  end if;
  if legislature_number_filter is not null and legislature_number_filter < 1 then
    raise exception 'numero de legislatura invalido'
      using errcode = '22023';
  end if;

  return query
  with selected_years as (
    select
      term.sphere,
      term.legislature_number,
      generated_year::smallint as fiscal_year
    from political.legislative_terms as term
    cross join lateral generate_series(
      term.full_fiscal_year_from::integer,
      term.full_fiscal_year_to::integer
    ) as generated_year
    where (sphere_filter is null or term.sphere = sphere_filter)
      and (
        legislature_number_filter is null
        or term.legislature_number = legislature_number_filter
      )
  ), federal_observed as (
    select
      transfer.fiscal_year,
      count(*)::integer as contribution_count,
      count(distinct transfer.author_key)::integer as author_count,
      count(*) filter (
        where (
          transfer.current_source_url ~ '^https://'
          and transfer.current_artifact_sha256 ~ '^[0-9a-f]{64}$'
        ) or (
          transfer.historical_source_url ~ '^https://'
          and transfer.historical_artifact_sha256 ~ '^[0-9a-f]{64}$'
        )
      )::integer as primary_evidence_count
    from territory.reconciled_parliamentary_transfers as transfer
    where transfer.author_kind = 'person'
      and transfer.reconciliation_status not like 'conflict_%'
      and transfer.destination_amount is not null
    group by transfer.fiscal_year
  ), state_observed as (
    select
      amendment.fiscal_year,
      count(*)::integer as contribution_count,
      count(distinct amendment.author_key)::integer as author_count,
      count(*) filter (
        where amendment.loa_source_url ~ '^https://'
          and amendment.loa_source_artifact_sha256 ~ '^[0-9a-f]{64}$'
      )::integer as primary_evidence_count
    from territory.bahia_state_loa_execution_reconciliation_snapshot
      as amendment
    group by amendment.fiscal_year
  )
  select
    expected.sphere,
    expected.legislature_number,
    expected.fiscal_year,
    case
      when expected.sphere = 'federal'
        and coalesce(federal.contribution_count, 0) > 0 then 'observed'
      when expected.sphere = 'state'
        and coalesce(state.contribution_count, 0) > 0 then 'observed'
      else 'not_observed'
    end::text as observation_status,
    case expected.sphere
      when 'federal' then coalesce(federal.contribution_count, 0)
      else coalesce(state.contribution_count, 0)
    end::integer as contribution_count,
    case expected.sphere
      when 'federal' then coalesce(federal.author_count, 0)
      else coalesce(state.author_count, 0)
    end::integer as author_count,
    case expected.sphere
      when 'federal' then coalesce(federal.primary_evidence_count, 0)
      else coalesce(state.primary_evidence_count, 0)
    end::integer as primary_evidence_count,
    'parliamentary-legislature-year-coverage/1.0.0'::text
      as methodology_version
  from selected_years as expected
  left join federal_observed as federal
    on expected.sphere = 'federal'
   and federal.fiscal_year = expected.fiscal_year
  left join state_observed as state
    on expected.sphere = 'state'
   and state.fiscal_year = expected.fiscal_year
  order by
    case expected.sphere when 'state' then 0 else 1 end,
    expected.legislature_number desc,
    expected.fiscal_year;
end;
$function$;

revoke all on function api.get_public_parliamentary_legislature_year_coverage(
  text, smallint
) from public;
grant execute on function api.get_public_parliamentary_legislature_year_coverage(
  text, smallint
) to anon, authenticated;

comment on function api.get_public_parliamentary_legislature_year_coverage(
  text, smallint
) is
  'Explicita, ano a ano, se o ranking encontrou contribuicoes individuais com evidencia; not_observed nao significa valor zero nem prova de ausencia oficial.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:expose-legislature-ranking-year-coverage',
  'methodology.legislature_ranking_year_coverage_published',
  'api.get_public_parliamentary_legislature_year_coverage',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'parliamentary-legislature-year-coverage/1.0.0',
    'statuses', array['observed', 'not_observed']
  ),
  jsonb_build_object(
    'not_observed_means_zero', false,
    'not_observed_means_source_absence', false
  )
);

notify pgrst, 'reload schema';

commit;
