begin;

create function api.get_public_parliamentary_legislature_contributions(
  sphere_filter text,
  legislature_number_filter smallint,
  author_key_filter text,
  page_size integer default 25,
  page_offset integer default 0
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
  author_key text,
  author_name text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  total_amendment_count integer,
  total_ranking_amount numeric(20,2),
  total_committed_amount numeric(20,2),
  total_liquidated_amount numeric(20,2),
  total_paid_amount numeric(20,2),
  row_position integer,
  contribution_key text,
  fiscal_year smallint,
  amendment_number text,
  beneficiary_name text,
  object_description text,
  ranking_amount numeric(20,2),
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  execution_status text,
  primary_source_url text,
  primary_artifact_sha256 text,
  secondary_source_url text,
  secondary_artifact_sha256 text,
  evidence_excerpt text,
  page_number integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  normalized_author_key text := lower(regexp_replace(
    nullif(btrim(author_key_filter), ''),
    '[[:space:]]+',
    ' ',
    'g'
  ));
begin
  if sphere_filter not in ('federal', 'state') then
    raise exception 'esfera legislativa deve ser federal ou state'
      using errcode = '22023';
  end if;
  if legislature_number_filter is null or legislature_number_filter < 1 then
    raise exception 'numero de legislatura invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is null or length(normalized_author_key) > 200 then
    raise exception 'autor legislativo invalido'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 100 then
    raise exception 'limite de contribuicoes deve estar entre 1 e 100'
      using errcode = '22023';
  end if;
  if page_offset is null or page_offset < 0 or page_offset > 10000 then
    raise exception 'deslocamento de contribuicoes invalido'
      using errcode = '22023';
  end if;

  return query
  with selected_term as (
    select term.*
    from political.legislative_terms as term
    where term.sphere = sphere_filter
      and term.legislature_number = legislature_number_filter
  ), federal_rows as (
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
      'destination'::text as ranking_amount_stage,
      contribution.author_key,
      contribution.author_name,
      contribution.reconciliation_key as contribution_key,
      contribution.fiscal_year,
      contribution.amendment_number,
      contribution.beneficiary_name,
      contribution.object_description,
      contribution.destination_amount::numeric(20,2) as ranking_amount,
      contribution.committed_amount::numeric(20,2) as committed_amount,
      null::numeric(20,2) as liquidated_amount,
      contribution.paid_amount::numeric(20,2) as paid_amount,
      contribution.reconciliation_status as execution_status,
      coalesce(
        contribution.current_source_url,
        contribution.historical_source_url
      ) as primary_source_url,
      coalesce(
        contribution.current_artifact_sha256,
        contribution.historical_artifact_sha256
      ) as primary_artifact_sha256,
      case
        when contribution.current_source_url is not null
          then contribution.historical_source_url
        else null
      end as secondary_source_url,
      case
        when contribution.current_source_url is not null
          then contribution.historical_artifact_sha256
        else null
      end as secondary_artifact_sha256,
      null::text as evidence_excerpt,
      null::integer as page_number
    from selected_term as term
    join territory.reconciled_parliamentary_transfers as contribution
      on term.sphere = 'federal'
     and contribution.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
     and contribution.author_kind = 'person'
     and contribution.author_key = normalized_author_key
    where contribution.reconciliation_status not like 'conflict_%'
      and contribution.destination_amount is not null
      and coalesce(
        contribution.current_source_url,
        contribution.historical_source_url
      ) ~ '^https://'
      and coalesce(
        contribution.current_artifact_sha256,
        contribution.historical_artifact_sha256
      ) ~ '^[0-9a-f]{64}$'
  ), state_rows as (
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
      'authorized'::text as ranking_amount_stage,
      contribution.author_key,
      contribution.author_name,
      format(
        'state:%s:%s:%s',
        contribution.fiscal_year,
        contribution.amendment_number,
        contribution.loa_evidence_sha256
      ) as contribution_key,
      contribution.fiscal_year,
      contribution.amendment_number,
      null::text as beneficiary_name,
      contribution.official_description as object_description,
      contribution.authorized_amount::numeric(20,2) as ranking_amount,
      contribution.committed_amount::numeric(20,2) as committed_amount,
      contribution.liquidated_amount::numeric(20,2) as liquidated_amount,
      contribution.paid_amount::numeric(20,2) as paid_amount,
      case contribution.reconciliation_status
        when 'matched_bidirectional_unique' then 'execution_confirmed'
        when 'blocked_non_unique_loa_key' then 'ambiguous_official_key'
        when 'blocked_non_unique_execution_key' then 'ambiguous_official_key'
        when 'not_found_in_execution_source'
          then 'not_found_in_execution_source'
        when 'blocked_scope_year_not_indexed'
          then 'official_link_key_unavailable'
        else 'scope_not_available'
      end as execution_status,
      contribution.loa_source_url as primary_source_url,
      contribution.loa_source_artifact_sha256 as primary_artifact_sha256,
      contribution.execution_source_url as secondary_source_url,
      contribution.execution_source_artifact_sha256
        as secondary_artifact_sha256,
      left(contribution.loa_evidence_text, 1200) as evidence_excerpt,
      contribution.page_number
    from selected_term as term
    join territory.bahia_state_loa_execution_reconciliation_snapshot
      as contribution
      on term.sphere = 'state'
     and contribution.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
     and contribution.author_key = normalized_author_key
    where contribution.loa_source_url ~ '^https://'
      and contribution.loa_source_artifact_sha256 ~ '^[0-9a-f]{64}$'
  ), contribution_rows as (
    select * from federal_rows
    union all
    select * from state_rows
  ), linked as (
    select
      contribution.*,
      coalesce(crosswalk.official_author_name, contribution.author_name)
        as display_author_name,
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      case
        when crosswalk.author_key is not null
          then 'approved_official_crosswalk'
        else 'not_linked'
      end as association_status
    from contribution_rows as contribution
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
     and crosswalk.author_key = contribution.author_key
     and crosswalk.review_status = 'approved'
  ), numbered as (
    select
      linked.*,
      count(*) over ()::integer as total_amendment_count,
      sum(linked.ranking_amount) over ()::numeric(20,2)
        as total_ranking_amount,
      sum(linked.committed_amount) over ()::numeric(20,2)
        as total_committed_amount,
      sum(linked.liquidated_amount) over ()::numeric(20,2)
        as total_liquidated_amount,
      sum(linked.paid_amount) over ()::numeric(20,2)
        as total_paid_amount,
      row_number() over (
        order by
          linked.fiscal_year desc,
          linked.ranking_amount desc,
          linked.amendment_number,
          linked.contribution_key
      )::integer as row_position
    from linked
  )
  select
    numbered.sphere,
    numbered.legislature_number,
    numbered.legislature_label,
    numbered.begins_on,
    numbered.ends_on,
    numbered.full_fiscal_year_from,
    numbered.full_fiscal_year_to,
    numbered.official_source_url,
    numbered.official_source_note,
    numbered.excluded_transition_years,
    numbered.ranking_amount_stage,
    numbered.author_key,
    numbered.display_author_name,
    numbered.representative_source_kind,
    numbered.representative_external_id,
    numbered.representative_profile_url,
    numbered.association_status,
    numbered.total_amendment_count,
    numbered.total_ranking_amount,
    numbered.total_committed_amount,
    numbered.total_liquidated_amount,
    numbered.total_paid_amount,
    numbered.row_position,
    numbered.contribution_key,
    numbered.fiscal_year,
    numbered.amendment_number,
    numbered.beneficiary_name,
    numbered.object_description,
    numbered.ranking_amount,
    numbered.committed_amount,
    numbered.liquidated_amount,
    numbered.paid_amount,
    numbered.execution_status,
    numbered.primary_source_url,
    numbered.primary_artifact_sha256,
    numbered.secondary_source_url,
    numbered.secondary_artifact_sha256,
    numbered.evidence_excerpt,
    numbered.page_number,
    'parliamentary-legislature-contributions/1.0.0'::text
  from numbered
  where numbered.row_position > page_offset
    and numbered.row_position <= page_offset + page_size
  order by numbered.row_position;
end;
$function$;

revoke all on function api.get_public_parliamentary_legislature_contributions(
  text, smallint, text, integer, integer
) from public;
grant execute on function api.get_public_parliamentary_legislature_contributions(
  text, smallint, text, integer, integer
) to anon, authenticated;

comment on function api.get_public_parliamentary_legislature_contributions(
  text, smallint, text, integer, integer
) is
  'Publica emendas de uma autoria individual em uma legislatura, com valores e evidencias separados por estagio e paginacao limitada.';

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
  'migration:publish-parliamentary-contribution-profiles',
  'methodology.parliamentary_contribution_profiles_published',
  'api.get_public_parliamentary_legislature_contributions',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'parliamentary-legislature-contributions/1.0.0',
    'federal_source', 'territory.reconciled_parliamentary_transfers',
    'state_source',
    'territory.bahia_state_loa_execution_reconciliation_snapshot'
  ),
  jsonb_build_object(
    'maximum_page_size', 100,
    'transition_years_inherited_from_legislative_terms', true
  )
);

notify pgrst, 'reload schema';

commit;
