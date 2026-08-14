begin;

create function api.get_public_parliamentary_legislature_coverage(
  sphere_filter text default null,
  legislature_number_filter smallint default null
)
returns table (
  sphere text,
  legislature_number smallint,
  legislature_label text,
  begins_on date,
  ends_on date,
  full_fiscal_year_from smallint,
  full_fiscal_year_to smallint,
  official_source_url text,
  official_source_note text,
  excluded_transition_years smallint[],
  ranking_amount_stage text,
  contribution_count integer,
  author_count integer,
  linked_author_count integer,
  unlinked_author_count integer,
  with_object_count integer,
  object_field_status text,
  with_beneficiary_count integer,
  beneficiary_field_status text,
  with_committed_count integer,
  with_liquidated_count integer,
  liquidated_field_status text,
  with_paid_count integer,
  execution_confirmed_count integer,
  execution_unresolved_count integer,
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
  with selected_terms as (
    select term.*
    from political.legislative_terms as term
    where (sphere_filter is null or term.sphere = sphere_filter)
      and (
        legislature_number_filter is null
        or term.legislature_number = legislature_number_filter
      )
  ), federal_coverage as (
    select
      term.sphere,
      term.legislature_number,
      count(*)::integer as contribution_count,
      count(distinct transfer.author_key)::integer as author_count,
      count(distinct transfer.author_key) filter (
        where crosswalk.author_key is not null
      )::integer as linked_author_count,
      count(distinct transfer.author_key) filter (
        where crosswalk.author_key is null
      )::integer as unlinked_author_count,
      count(*) filter (
        where nullif(btrim(transfer.object_description), '') is not null
      )::integer as with_object_count,
      count(*) filter (
        where nullif(btrim(transfer.beneficiary_name), '') is not null
      )::integer as with_beneficiary_count,
      count(*) filter (
        where transfer.committed_amount is not null
      )::integer as with_committed_count,
      count(*) filter (
        where transfer.paid_amount is not null
      )::integer as with_paid_count,
      count(*) filter (
        where transfer.reconciliation_status = 'matched_exact'
      )::integer as execution_confirmed_count,
      count(*) filter (
        where transfer.reconciliation_status is distinct from 'matched_exact'
      )::integer as execution_unresolved_count,
      count(*) filter (
        where (
          transfer.current_source_url ~ '^https://'
          and transfer.current_artifact_sha256 ~ '^[0-9a-f]{64}$'
        ) or (
          transfer.historical_source_url ~ '^https://'
          and transfer.historical_artifact_sha256 ~ '^[0-9a-f]{64}$'
        )
      )::integer as primary_evidence_count
    from selected_terms as term
    join territory.reconciled_parliamentary_transfers as transfer
      on term.sphere = 'federal'
     and transfer.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
     and crosswalk.author_key = transfer.author_key
     and crosswalk.review_status = 'approved'
    where transfer.author_kind = 'person'
      and transfer.reconciliation_status not like 'conflict_%'
      and transfer.destination_amount is not null
    group by term.sphere, term.legislature_number
  ), state_coverage as (
    select
      term.sphere,
      term.legislature_number,
      count(*)::integer as contribution_count,
      count(distinct amendment.author_key)::integer as author_count,
      count(distinct amendment.author_key) filter (
        where crosswalk.author_key is not null
      )::integer as linked_author_count,
      count(distinct amendment.author_key) filter (
        where crosswalk.author_key is null
      )::integer as unlinked_author_count,
      count(*) filter (
        where nullif(btrim(amendment.official_description), '') is not null
      )::integer as with_object_count,
      count(*) filter (
        where amendment.committed_amount is not null
      )::integer as with_committed_count,
      count(*) filter (
        where amendment.liquidated_amount is not null
      )::integer as with_liquidated_count,
      count(*) filter (
        where amendment.paid_amount is not null
      )::integer as with_paid_count,
      count(*) filter (
        where amendment.reconciliation_status = 'matched_bidirectional_unique'
      )::integer as execution_confirmed_count,
      count(*) filter (
        where amendment.reconciliation_status is distinct from
          'matched_bidirectional_unique'
      )::integer as execution_unresolved_count,
      count(*) filter (
        where amendment.loa_source_url ~ '^https://'
          and amendment.loa_source_artifact_sha256 ~ '^[0-9a-f]{64}$'
      )::integer as primary_evidence_count
    from selected_terms as term
    join territory.bahia_state_loa_execution_reconciliation_snapshot as amendment
      on term.sphere = 'state'
     and amendment.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
     and crosswalk.author_key = amendment.author_key
     and crosswalk.review_status = 'approved'
    group by term.sphere, term.legislature_number
  ), coverage as (
    select
      federal.sphere,
      federal.legislature_number,
      federal.contribution_count,
      federal.author_count,
      federal.linked_author_count,
      federal.unlinked_author_count,
      federal.with_object_count,
      federal.with_beneficiary_count,
      federal.with_committed_count,
      null::integer as with_liquidated_count,
      federal.with_paid_count,
      federal.execution_confirmed_count,
      federal.execution_unresolved_count,
      federal.primary_evidence_count
    from federal_coverage as federal
    union all
    select
      state.sphere,
      state.legislature_number,
      state.contribution_count,
      state.author_count,
      state.linked_author_count,
      state.unlinked_author_count,
      state.with_object_count,
      null::integer as with_beneficiary_count,
      state.with_committed_count,
      state.with_liquidated_count,
      state.with_paid_count,
      state.execution_confirmed_count,
      state.execution_unresolved_count,
      state.primary_evidence_count
    from state_coverage as state
  )
  select
    term.sphere,
    term.legislature_number,
    term.legislature_label,
    term.begins_on,
    term.ends_on,
    term.full_fiscal_year_from,
    term.full_fiscal_year_to,
    term.official_source_url,
    term.official_source_note,
    term.excluded_transition_years,
    case term.sphere when 'federal' then 'destination' else 'authorized' end,
    coalesce(coverage.contribution_count, 0),
    coalesce(coverage.author_count, 0),
    coalesce(coverage.linked_author_count, 0),
    coalesce(coverage.unlinked_author_count, 0),
    coalesce(coverage.with_object_count, 0),
    'published_by_source'::text,
    case term.sphere
      when 'federal' then coalesce(coverage.with_beneficiary_count, 0)
      else null
    end,
    case term.sphere
      when 'federal' then 'published_by_source'
      else 'not_published_in_source'
    end::text,
    coalesce(coverage.with_committed_count, 0),
    case term.sphere
      when 'state' then coalesce(coverage.with_liquidated_count, 0)
      else null
    end,
    case term.sphere
      when 'state' then 'published_by_source'
      else 'not_published_in_source'
    end::text,
    coalesce(coverage.with_paid_count, 0),
    coalesce(coverage.execution_confirmed_count, 0),
    coalesce(coverage.execution_unresolved_count, 0),
    coalesce(coverage.primary_evidence_count, 0),
    'parliamentary-legislature-coverage/1.0.0'::text
  from selected_terms as term
  left join coverage
    on coverage.sphere = term.sphere
   and coverage.legislature_number = term.legislature_number
  order by
    case term.sphere when 'state' then 0 else 1 end,
    term.legislature_number desc;
end;
$function$;

revoke all on function api.get_public_parliamentary_legislature_coverage(
  text, smallint
) from public;
grant execute on function api.get_public_parliamentary_legislature_coverage(
  text, smallint
) to anon, authenticated;

comment on function api.get_public_parliamentary_legislature_coverage(
  text, smallint
) is
  'Publica contagens de cobertura observada por legislatura, diferenciando zero de campo nao publicado pela fonte.';

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
  'migration:publish-parliamentary-legislature-coverage',
  'methodology.parliamentary_legislature_coverage_published',
  'api.get_public_parliamentary_legislature_coverage',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'parliamentary-legislature-coverage/1.0.0',
    'identity_linkage', 'approved_official_crosswalk_only',
    'federal_liquidated_field', 'not_published_in_source',
    'state_beneficiary_field', 'not_published_in_source'
  ),
  jsonb_build_object(
    'publishes_personal_identifiers', false,
    'publishes_aggregate_counts_only', true
  )
);

notify pgrst, 'reload schema';

commit;
