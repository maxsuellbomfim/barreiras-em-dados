begin;

create function api.get_public_bahia_state_loa_representative_contributions(
  page_size integer default 100
)
returns table (
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  author_key text,
  author_name text,
  fiscal_year smallint,
  amendment_count integer,
  authorized_amount numeric(20,2),
  matched_amendment_count integer,
  matched_authorized_amount numeric(20,2),
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  blocked_amendment_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite das contribuicoes estaduais por representante invalido'
      using errcode = '22023';
  end if;

  return query
  with linked as (
    select
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      reconciliation.author_key,
      reconciliation.author_name,
      reconciliation.fiscal_year,
      reconciliation.amendment_number,
      reconciliation.authorized_amount,
      reconciliation.reconciliation_status,
      reconciliation.committed_amount,
      reconciliation.liquidated_amount,
      reconciliation.paid_amount
    from territory.bahia_state_loa_execution_reconciliation as reconciliation
    join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
      and crosswalk.author_key = reconciliation.author_key
      and crosswalk.review_status = 'approved'
  ), grouped as (
    select
      linked.representative_source_kind,
      linked.representative_external_id,
      linked.representative_profile_url,
      linked.author_key,
      (array_agg(
        linked.author_name
        order by linked.amendment_number, linked.author_name
      ))[1] as author_name,
      linked.fiscal_year,
      count(*)::integer as amendment_count,
      sum(linked.authorized_amount)::numeric(20,2) as authorized_amount,
      count(*) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::integer as matched_amendment_count,
      sum(linked.authorized_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as matched_authorized_amount,
      sum(linked.committed_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as committed_amount,
      sum(linked.liquidated_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as liquidated_amount,
      sum(linked.paid_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as paid_amount,
      count(*) filter (
        where linked.reconciliation_status <> 'matched_bidirectional_unique'
      )::integer as blocked_amendment_count
    from linked
    group by
      linked.representative_source_kind,
      linked.representative_external_id,
      linked.representative_profile_url,
      linked.author_key,
      linked.fiscal_year
  )
  select
    grouped.representative_source_kind,
    grouped.representative_external_id,
    grouped.representative_profile_url,
    grouped.author_key,
    grouped.author_name,
    grouped.fiscal_year,
    grouped.amendment_count,
    grouped.authorized_amount,
    grouped.matched_amendment_count,
    grouped.matched_authorized_amount,
    grouped.committed_amount,
    grouped.liquidated_amount,
    grouped.paid_amount,
    grouped.blocked_amendment_count,
    'bahia-state-loa-representative-contributions/1.0.0'::text
  from grouped
  order by
    grouped.representative_source_kind,
    grouped.representative_external_id,
    grouped.fiscal_year desc,
    grouped.author_key
  limit page_size;
end;
$$;

revoke all on function api.get_public_bahia_state_loa_representative_contributions(
  integer
) from public;
grant execute on function api.get_public_bahia_state_loa_representative_contributions(
  integer
) to anon, authenticated;

comment on function api.get_public_bahia_state_loa_representative_contributions(
  integer
) is
  'Linha do tempo anual por perfil oficialmente ligado; autorizado cobre todas as emendas e execucao somente o subconjunto com chave unica.';

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
  'migration:publish-state-loa-representative-contributions',
  'territory.representative_contributions_published',
  'api.get_public_bahia_state_loa_representative_contributions',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'bahia-state-loa-representative-contributions/1.0.0',
    'grouping', 'representative_and_fiscal_year'
  ),
  jsonb_build_object(
    'authorized_universe', 'all_territorial_amendments',
    'execution_universe', 'matched_bidirectional_unique_only',
    'unmatched_values_are_null', true
  )
);

notify pgrst, 'reload schema';

commit;
