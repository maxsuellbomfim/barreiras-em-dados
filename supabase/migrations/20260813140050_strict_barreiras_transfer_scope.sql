begin;

create view territory.federal_transfer_proposal_scope
with (security_barrier = true)
as
select
  proposal.proposal_id,
  case
    when proposal.object_description
      ~* '(^|[^[:alnum:]])barreiras([^[:alnum:]]|$)'
      then 'object_explicitly_mentions_barreiras'
    when proposal.proponent_name ~* 'cons[oó]rcio'
      then 'regional_entity_destination_unverified'
    when proposal.proponent_name
      ~* '(^|[^[:alnum:]])barreiras([^[:alnum:]]|$)'
      then 'municipal_entity_named_barreiras'
    else 'recipient_registered_in_barreiras'
  end as territorial_evidence_status,
  case
    when proposal.object_description
      ~* '(^|[^[:alnum:]])barreiras([^[:alnum:]]|$)'
      then true
    when proposal.proponent_name ~* 'cons[oó]rcio'
      then false
    else true
  end as is_confirmed_for_barreiras
from territory.federal_transfer_proposals as proposal;

revoke all on territory.federal_transfer_proposal_scope from public;
revoke all on territory.federal_transfer_proposal_scope
  from anon, authenticated;

drop function api.get_public_federal_transfer_proposals(
  smallint, text, integer
);

create function api.get_public_federal_transfer_proposals(
  fiscal_year_filter smallint default null,
  proposal_status_filter text default null,
  page_size integer default 100
)
returns table (
  proposal_id text,
  proposal_number text,
  fiscal_year smallint,
  proposal_date_text text,
  proposal_status text,
  basic_project_status text,
  modality text,
  object_description text,
  investment_item text,
  proponent_name text,
  federal_body_name text,
  superior_federal_body_name text,
  global_amount numeric(20,2),
  requested_transfer_amount numeric(20,2),
  counterpart_amount numeric(20,2),
  authorship_status text,
  financial_stage text,
  collected_at timestamptz,
  source_url text,
  artifact_sha256 text,
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
  normalized_status text := nullif(btrim(proposal_status_filter), '');
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de propostas invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2021 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano de proposta invalido'
      using errcode = '22023';
  end if;
  if normalized_status is not null and length(normalized_status) > 200 then
    raise exception 'situacao de proposta invalida'
      using errcode = '22023';
  end if;

  return query
  select
    proposal.proposal_id,
    proposal.proposal_number,
    proposal.fiscal_year,
    proposal.proposal_date_text,
    proposal.proposal_status,
    proposal.basic_project_status,
    proposal.modality,
    proposal.object_description,
    proposal.investment_item,
    proposal.proponent_name,
    proposal.federal_body_name,
    proposal.superior_federal_body_name,
    proposal.global_amount,
    proposal.requested_transfer_amount,
    proposal.counterpart_amount,
    proposal.authorship_status,
    proposal.financial_stage,
    proposal.collected_at,
    proposal.source_url,
    proposal.artifact_sha256,
    'federal-transfer-proposals/1.0.0'::text
  from territory.federal_transfer_proposals as proposal
  join territory.federal_transfer_proposal_scope as scope
    on scope.proposal_id = proposal.proposal_id
   and scope.is_confirmed_for_barreiras
  where (fiscal_year_filter is null or proposal.fiscal_year = fiscal_year_filter)
    and (
      normalized_status is null
      or lower(proposal.proposal_status) = lower(normalized_status)
    )
  order by
    proposal.fiscal_year desc,
    proposal.proposal_date_text desc nulls last,
    proposal.proposal_number desc nulls last,
    proposal.proposal_id desc
  limit page_size;
end;
$$;

drop function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
);

create function api.get_public_historical_parliamentary_amendments(
  fiscal_year_filter smallint default null,
  author_kind_filter text default null,
  page_size integer default 100
)
returns table (
  external_transfer_key text,
  proposal_id text,
  proposal_number text,
  fiscal_year smallint,
  amendment_number text,
  author_name text,
  author_kind text,
  amendment_kind text,
  program_code text,
  is_mandatory boolean,
  destination_amount numeric(20,2),
  amendment_total_in_source numeric(20,2),
  beneficiary_name text,
  object_description text,
  proposal_status text,
  financial_stage text,
  collected_at timestamptz,
  source_url text,
  artifact_sha256 text,
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
    raise exception 'limite de emendas historicas invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2021 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano de emenda historica invalido'
      using errcode = '22023';
  end if;
  if author_kind_filter is not null
    and author_kind_filter not in (
      'person', 'commission', 'bench', 'collective', 'other'
    )
  then
    raise exception 'tipo de autoria historica invalido'
      using errcode = '22023';
  end if;

  return query
  select
    amendment.external_transfer_key,
    amendment.proposal_id,
    amendment.proposal_number,
    amendment.fiscal_year,
    amendment.amendment_number,
    amendment.author_name,
    amendment.author_kind,
    amendment.amendment_kind,
    amendment.program_code,
    amendment.is_mandatory,
    amendment.destination_amount,
    amendment.amendment_total_in_source,
    amendment.beneficiary_name,
    amendment.object_description,
    amendment.proposal_status,
    amendment.financial_stage,
    amendment.collected_at,
    amendment.source_url,
    amendment.artifact_sha256,
    'historical-parliamentary-amendments/1.0.0'::text
  from territory.historical_parliamentary_amendments as amendment
  join territory.federal_transfer_proposal_scope as scope
    on scope.proposal_id = amendment.proposal_id
   and scope.is_confirmed_for_barreiras
  where (
    fiscal_year_filter is null
    or amendment.fiscal_year = fiscal_year_filter
  )
    and (
      author_kind_filter is null
      or amendment.author_kind = author_kind_filter
    )
  order by
    amendment.fiscal_year desc,
    amendment.destination_amount desc,
    amendment.author_name,
    amendment.amendment_number
  limit page_size;
end;
$$;

drop function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
);

create function api.get_public_historical_parliamentary_amendment_ranking(
  author_scope text default 'person',
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_kind text,
  amendment_count integer,
  proposal_count integer,
  destination_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  financial_stage text,
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
    raise exception 'limite de ranking historico invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      amendment.author_key,
      max(amendment.author_name) as author_name,
      amendment.author_kind,
      count(distinct coalesce(
        amendment.amendment_number,
        amendment.external_transfer_key
      ))::integer as amendment_count,
      count(distinct amendment.proposal_id)::integer as proposal_count,
      sum(amendment.destination_amount)::numeric(20,2) as destination_amount,
      min(amendment.fiscal_year)::smallint as first_year,
      max(amendment.fiscal_year)::smallint as last_year
    from territory.historical_parliamentary_amendments as amendment
    join territory.federal_transfer_proposal_scope as scope
      on scope.proposal_id = amendment.proposal_id
     and scope.is_confirmed_for_barreiras
    where (
      fiscal_year_filter is null
      or amendment.fiscal_year = fiscal_year_filter
    )
      and (
        (author_scope = 'person' and amendment.author_kind = 'person')
        or
        (author_scope = 'collective' and amendment.author_kind in (
          'commission', 'bench', 'collective'
        ))
      )
    group by amendment.author_key, amendment.author_kind
  ), ranked as (
    select
      row_number() over (
        order by grouped.destination_amount desc, grouped.author_name
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_kind,
    ranked.amendment_count,
    ranked.proposal_count,
    ranked.destination_amount,
    ranked.first_year,
    ranked.last_year,
    'destination_identified_payment_not_verified'::text,
    'historical-parliamentary-amendment-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

create function api.get_public_federal_transfer_scope_summary()
returns table (
  candidate_proposal_count integer,
  included_proposal_count integer,
  excluded_regional_proposal_count integer,
  candidate_amendment_count integer,
  included_amendment_count integer,
  excluded_regional_amendment_count integer,
  excluded_regional_destination_amount numeric(20,2),
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    count(distinct scope.proposal_id)::integer,
    count(distinct scope.proposal_id) filter (
      where scope.is_confirmed_for_barreiras
    )::integer,
    count(distinct scope.proposal_id) filter (
      where not scope.is_confirmed_for_barreiras
    )::integer,
    count(amendment.external_transfer_key)::integer,
    count(amendment.external_transfer_key) filter (
      where scope.is_confirmed_for_barreiras
    )::integer,
    count(amendment.external_transfer_key) filter (
      where not scope.is_confirmed_for_barreiras
    )::integer,
    coalesce(sum(amendment.destination_amount) filter (
      where not scope.is_confirmed_for_barreiras
    ), 0)::numeric(20,2),
    'federal-transfer-territorial-scope/1.0.0'::text
  from territory.federal_transfer_proposal_scope as scope
  left join territory.historical_parliamentary_amendments as amendment
    on amendment.proposal_id = scope.proposal_id;
$$;

revoke all on function api.get_public_federal_transfer_proposals(
  smallint, text, integer
) from public;
revoke all on function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
) from public;
revoke all on function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
) from public;
revoke all on function api.get_public_federal_transfer_scope_summary()
  from public;

grant execute on function api.get_public_federal_transfer_proposals(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
) to anon, authenticated;
grant execute on function api.get_public_federal_transfer_scope_summary()
  to anon, authenticated;

comment on view territory.federal_transfer_proposal_scope is
  'Classifica evidencia territorial sem atribuir automaticamente consorcios regionais a Barreiras.';
comment on function api.get_public_federal_transfer_scope_summary() is
  'Explica quantos registros regionais foram preservados, mas excluidos dos totais de Barreiras.';

notify pgrst, 'reload schema';

commit;
