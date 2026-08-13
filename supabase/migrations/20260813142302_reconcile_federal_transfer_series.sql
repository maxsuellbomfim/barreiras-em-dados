begin;

-- Consolida a serie corrente da API e o arquivo historico do Transferegov.
-- Uma linha so e fundida quando proposta e numero de emenda coincidem. Se as
-- fontes divergirem em autoria, ano, tipo ou valor, o registro permanece
-- visivel como conflito e nao participa de totais nem rankings.
create view territory.reconciled_parliamentary_transfers
with (security_barrier = true)
as
with current_rows as (
  select
    case
      when nullif(btrim(transfer.proposal_id), '') is not null
        and nullif(btrim(transfer.amendment_number), '') is not null
      then 'official:' || btrim(transfer.proposal_id) || ':'
        || lower(btrim(transfer.amendment_number))
      else 'current:' || transfer.external_transfer_key
    end as reconciliation_key,
    transfer.*
  from territory.parliamentary_transfers as transfer
), current_grouped as (
  select
    reconciliation_key,
    count(*)::integer as source_row_count,
    max(external_transfer_key) as external_transfer_key,
    max(proposal_id) as proposal_id,
    max(fiscal_year) as fiscal_year,
    max(amendment_number) as amendment_number,
    max(author_name) as author_name,
    max(author_key) as author_key,
    max(author_kind) as author_kind,
    max(beneficiary_name) as beneficiary_name,
    max(object_description) as object_description,
    max(destination_amount)::numeric(20,2) as destination_amount,
    max(committed_amount)::numeric(20,2) as committed_amount,
    max(paid_amount)::numeric(20,2) as paid_amount,
    max(stage_attribution_status) as stage_attribution_status,
    max(collected_at) as collected_at,
    max(source_url) as source_url,
    max(artifact_sha256) as artifact_sha256
  from current_rows
  group by reconciliation_key
), historical_rows as (
  select
    case
      when nullif(btrim(amendment.proposal_id), '') is not null
        and nullif(btrim(amendment.amendment_number), '') is not null
      then 'official:' || btrim(amendment.proposal_id) || ':'
        || lower(btrim(amendment.amendment_number))
      else 'historical:' || amendment.external_transfer_key
    end as reconciliation_key,
    amendment.*
  from territory.historical_parliamentary_amendments as amendment
  join territory.federal_transfer_proposal_scope as scope
    on scope.proposal_id = amendment.proposal_id
   and scope.is_confirmed_for_barreiras
), historical_grouped as (
  select
    reconciliation_key,
    count(*)::integer as source_row_count,
    max(external_transfer_key) as external_transfer_key,
    max(proposal_id) as proposal_id,
    max(proposal_number) as proposal_number,
    max(fiscal_year) as fiscal_year,
    max(amendment_number) as amendment_number,
    max(author_name) as author_name,
    max(author_key) as author_key,
    max(author_kind) as author_kind,
    max(beneficiary_name) as beneficiary_name,
    max(object_description) as object_description,
    max(destination_amount)::numeric(20,2) as destination_amount,
    max(financial_stage) as financial_stage,
    max(collected_at) as collected_at,
    max(source_url) as source_url,
    max(artifact_sha256) as artifact_sha256
  from historical_rows
  group by reconciliation_key
), joined as (
  select
    coalesce(current.reconciliation_key, historical.reconciliation_key)
      as reconciliation_key,
    current.source_row_count as current_source_row_count,
    historical.source_row_count as historical_source_row_count,
    current.external_transfer_key as current_external_transfer_key,
    historical.external_transfer_key as historical_external_transfer_key,
    coalesce(current.proposal_id, historical.proposal_id) as proposal_id,
    historical.proposal_number,
    coalesce(current.fiscal_year, historical.fiscal_year) as fiscal_year,
    coalesce(current.amendment_number, historical.amendment_number)
      as amendment_number,
    coalesce(historical.author_name, current.author_name) as author_name,
    coalesce(current.author_key, historical.author_key) as author_key,
    coalesce(current.author_kind, historical.author_kind) as author_kind,
    coalesce(current.beneficiary_name, historical.beneficiary_name)
      as beneficiary_name,
    coalesce(current.object_description, historical.object_description)
      as object_description,
    current.destination_amount as current_destination_amount,
    historical.destination_amount as historical_destination_amount,
    current.committed_amount,
    current.paid_amount,
    current.stage_attribution_status,
    current.collected_at as current_collected_at,
    historical.collected_at as historical_collected_at,
    current.source_url as current_source_url,
    current.artifact_sha256 as current_artifact_sha256,
    historical.source_url as historical_source_url,
    historical.artifact_sha256 as historical_artifact_sha256,
    current.fiscal_year as current_fiscal_year,
    historical.fiscal_year as historical_fiscal_year,
    current.author_key as current_author_key,
    historical.author_key as historical_author_key,
    current.author_kind as current_author_kind,
    historical.author_kind as historical_author_kind
  from current_grouped as current
  full outer join historical_grouped as historical
    on historical.reconciliation_key = current.reconciliation_key
), classified as (
  select
    joined.*,
    case
      when current_source_row_count is null then 'historical_only'
      when historical_source_row_count is null then 'current_only'
      when current_source_row_count <> 1 or historical_source_row_count <> 1
        then 'conflict_non_unique_official_key'
      when current_fiscal_year is distinct from historical_fiscal_year
        or current_author_key is distinct from historical_author_key
        or current_author_kind is distinct from historical_author_kind
        or current_destination_amount is distinct from historical_destination_amount
        then 'conflict_source_divergence'
      else 'matched_exact'
    end as reconciliation_status
  from joined
)
select
  reconciliation_key,
  current_external_transfer_key,
  historical_external_transfer_key,
  proposal_id,
  proposal_number,
  fiscal_year,
  amendment_number,
  author_name,
  author_key,
  author_kind,
  beneficiary_name,
  object_description,
  reconciliation_status,
  case
    when reconciliation_status like 'conflict_%' then null
    else coalesce(current_destination_amount, historical_destination_amount)
  end::numeric(20,2) as destination_amount,
  current_destination_amount,
  historical_destination_amount,
  case when reconciliation_status like 'conflict_%' then null
    else committed_amount end::numeric(20,2) as committed_amount,
  case when reconciliation_status like 'conflict_%' then null
    else paid_amount end::numeric(20,2) as paid_amount,
  case
    when reconciliation_status like 'conflict_%' then 'reconciliation_required'
    when current_external_transfer_key is not null then stage_attribution_status
    else 'destination_identified_payment_not_verified'
  end as financial_stage,
  current_collected_at,
  historical_collected_at,
  current_source_url,
  current_artifact_sha256,
  historical_source_url,
  historical_artifact_sha256,
  current_source_row_count,
  historical_source_row_count
from classified;

revoke all on territory.reconciled_parliamentary_transfers from public;
revoke all on territory.reconciled_parliamentary_transfers
  from anon, authenticated;

create function api.get_public_reconciled_parliamentary_transfers(
  fiscal_year_filter smallint default null,
  author_kind_filter text default null,
  page_size integer default 100
)
returns table (
  reconciliation_key text,
  proposal_id text,
  proposal_number text,
  fiscal_year smallint,
  amendment_number text,
  author_name text,
  author_kind text,
  beneficiary_name text,
  object_description text,
  reconciliation_status text,
  destination_amount numeric(20,2),
  current_destination_amount numeric(20,2),
  historical_destination_amount numeric(20,2),
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  financial_stage text,
  current_source_url text,
  current_artifact_sha256 text,
  historical_source_url text,
  historical_artifact_sha256 text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de emendas reconciliadas invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2021 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano de emenda reconciliada invalido'
      using errcode = '22023';
  end if;
  if author_kind_filter is not null
    and author_kind_filter not in (
      'person', 'commission', 'bench', 'collective', 'other'
    )
  then
    raise exception 'tipo de autoria reconciliada invalido'
      using errcode = '22023';
  end if;

  return query
  select
    transfer.reconciliation_key,
    transfer.proposal_id,
    transfer.proposal_number,
    transfer.fiscal_year,
    transfer.amendment_number,
    transfer.author_name,
    transfer.author_kind,
    transfer.beneficiary_name,
    transfer.object_description,
    transfer.reconciliation_status,
    transfer.destination_amount,
    transfer.current_destination_amount,
    transfer.historical_destination_amount,
    transfer.committed_amount,
    transfer.paid_amount,
    transfer.financial_stage,
    transfer.current_source_url,
    transfer.current_artifact_sha256,
    transfer.historical_source_url,
    transfer.historical_artifact_sha256,
    'reconciled-parliamentary-transfers/1.0.0'::text
  from territory.reconciled_parliamentary_transfers as transfer
  where (fiscal_year_filter is null or transfer.fiscal_year = fiscal_year_filter)
    and (author_kind_filter is null or transfer.author_kind = author_kind_filter)
  order by
    transfer.fiscal_year desc,
    transfer.destination_amount desc nulls last,
    transfer.author_name,
    transfer.amendment_number
  limit page_size;
end;
$$;

create function api.get_public_reconciled_parliamentary_transfer_ranking(
  author_scope text default 'person',
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_kind text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  amendment_count integer,
  proposal_count integer,
  destination_amount numeric(20,2),
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if author_scope not in ('person', 'collective') then
    raise exception 'author_scope deve ser person ou collective'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de ranking reconciliado invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      transfer.author_key,
      max(transfer.author_name) as author_name,
      transfer.author_kind,
      count(*)::integer as amendment_count,
      count(distinct transfer.proposal_id)::integer as proposal_count,
      sum(transfer.destination_amount)::numeric(20,2) as destination_amount,
      sum(transfer.committed_amount)::numeric(20,2) as committed_amount,
      sum(transfer.paid_amount)::numeric(20,2) as paid_amount,
      min(transfer.fiscal_year)::smallint as first_year,
      max(transfer.fiscal_year)::smallint as last_year
    from territory.reconciled_parliamentary_transfers as transfer
    where transfer.reconciliation_status not like 'conflict_%'
      and transfer.destination_amount is not null
      and (fiscal_year_filter is null or transfer.fiscal_year = fiscal_year_filter)
      and (
        (author_scope = 'person' and transfer.author_kind = 'person')
        or (author_scope = 'collective' and transfer.author_kind in (
          'commission', 'bench', 'collective'
        ))
      )
    group by transfer.author_key, transfer.author_kind
  ), linked as (
    select
      grouped.*,
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      case
        when grouped.author_kind <> 'person' then 'not_applicable_collective'
        when crosswalk.author_key is not null then 'approved_official_crosswalk'
        else 'not_linked'
      end as association_status
    from grouped
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = grouped.author_kind
     and crosswalk.author_key = grouped.author_key
     and crosswalk.review_status = 'approved'
  ), ranked as (
    select
      row_number() over (
        order by linked.destination_amount desc, linked.author_name
      )::integer as rank_position,
      linked.*
    from linked
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_kind,
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    ranked.association_status,
    ranked.amendment_count,
    ranked.proposal_count,
    ranked.destination_amount,
    ranked.committed_amount,
    ranked.paid_amount,
    ranked.first_year,
    ranked.last_year,
    'reconciled-parliamentary-transfer-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

create function api.get_public_parliamentary_transfer_reconciliation_summary()
returns table (
  current_source_row_count integer,
  historical_source_row_count integer,
  consolidated_row_count integer,
  exact_match_count integer,
  current_only_count integer,
  historical_only_count integer,
  conflict_count integer,
  rankable_row_count integer,
  published_destination_amount numeric(20,2),
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    (select count(*)::integer from territory.parliamentary_transfers),
    (select count(*)::integer
       from territory.historical_parliamentary_amendments as amendment
       join territory.federal_transfer_proposal_scope as scope
         on scope.proposal_id = amendment.proposal_id
        and scope.is_confirmed_for_barreiras),
    count(*)::integer,
    count(*) filter (where reconciliation_status = 'matched_exact')::integer,
    count(*) filter (where reconciliation_status = 'current_only')::integer,
    count(*) filter (where reconciliation_status = 'historical_only')::integer,
    count(*) filter (where reconciliation_status like 'conflict_%')::integer,
    count(*) filter (
      where reconciliation_status not like 'conflict_%'
        and destination_amount is not null
    )::integer,
    coalesce(sum(destination_amount) filter (
      where reconciliation_status not like 'conflict_%'
    ), 0)::numeric(20,2),
    'parliamentary-transfer-reconciliation/1.0.0'::text
  from territory.reconciled_parliamentary_transfers;
$$;

revoke all on function api.get_public_reconciled_parliamentary_transfers(
  smallint, text, integer
) from public;
revoke all on function api.get_public_reconciled_parliamentary_transfer_ranking(
  text, smallint, integer
) from public;
revoke all on function api.get_public_parliamentary_transfer_reconciliation_summary()
  from public;

grant execute on function api.get_public_reconciled_parliamentary_transfers(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_reconciled_parliamentary_transfer_ranking(
  text, smallint, integer
) to anon, authenticated;
grant execute on function api.get_public_parliamentary_transfer_reconciliation_summary()
  to anon, authenticated;

comment on view territory.reconciled_parliamentary_transfers is
  'Reconcilia series corrente e historica somente por identificadores oficiais; conflitos nao entram em totais.';
comment on function api.get_public_parliamentary_transfer_reconciliation_summary() is
  'Quantifica correspondencias, lacunas e conflitos entre as duas series federais.';

notify pgrst, 'reload schema';

commit;
