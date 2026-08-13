begin;

-- Projecao publica das emendas do arquivo historico oficial. Esta serie fica
-- separada da API corrente ate existir reconciliacao deterministica entre as
-- duas identificacoes oficiais, evitando dupla contagem no ranking principal.

create index if not exists raw_records_transferegov_historical_amendment_idx
  on raw.raw_records (
    source_record_key,
    collected_at desc,
    id desc
  )
  where record_type = 'transferegov_historical_amendment'
    and source_record_key is not null;

create view territory.latest_transferegov_historical_amendments
with (security_barrier = true)
as
select distinct on (record.source_record_key)
  record.id as raw_record_id,
  record.raw_artifact_id,
  record.source_record_key,
  record.payload,
  record.payload_sha256,
  record.collected_at
from raw.raw_records as record
where record.record_type = 'transferegov_historical_amendment'
  and record.source_record_key is not null
order by
  record.source_record_key,
  record.collected_at desc,
  record.id desc;

create view territory.historical_parliamentary_amendments
with (security_barrier = true)
as
select
  amendment.source_record_key as external_transfer_key,
  amendment.raw_record_id as origin_amendment_raw_record_id,
  proposal.raw_record_id as origin_proposal_raw_record_id,
  amendment.payload ->> 'id_proposta' as proposal_id,
  proposal.proposal_number,
  proposal.fiscal_year,
  nullif(btrim(amendment.payload ->> 'numero_emenda'), '') as amendment_number,
  nullif(btrim(amendment.payload ->> 'autor_nome'), '') as author_name,
  lower(regexp_replace(
    nullif(btrim(amendment.payload ->> 'autor_nome'), ''),
    '[[:space:]]+',
    ' ',
    'g'
  )) as author_key,
  case
    when lower(coalesce(amendment.payload ->> 'tipo_parlamentar', ''))
      like 'individual%'
      then 'person'
    when lower(coalesce(amendment.payload ->> 'tipo_parlamentar', ''))
      like 'comiss%'
      then 'commission'
    when lower(coalesce(amendment.payload ->> 'tipo_parlamentar', ''))
      like 'bancad%'
      then 'bench'
    when lower(coalesce(amendment.payload ->> 'tipo_parlamentar', ''))
      like 'coletiv%'
      then 'collective'
    else 'other'
  end as author_kind,
  nullif(btrim(amendment.payload ->> 'tipo_parlamentar'), '')
    as amendment_kind,
  nullif(btrim(amendment.payload ->> 'codigo_programa_emenda'), '')
    as program_code,
  case
    when lower(coalesce(amendment.payload ->> 'impositiva', '')) = 'true'
      then true
    when lower(coalesce(amendment.payload ->> 'impositiva', '')) = 'false'
      then false
  end as is_mandatory,
  case
    when amendment.payload ->> 'valor_repasse_emenda'
      ~ '^[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    then (amendment.payload ->> 'valor_repasse_emenda')::numeric(20,2)
  end as destination_amount,
  case
    when amendment.payload ->> 'valor_repasse_proposta_emenda'
      ~ '^[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    then (
      amendment.payload ->> 'valor_repasse_proposta_emenda'
    )::numeric(20,2)
  end as amendment_total_in_source,
  proposal.proponent_name as beneficiary_name,
  proposal.object_description,
  proposal.proposal_status,
  'destination_identified_payment_not_verified'::text as financial_stage,
  greatest(amendment.collected_at, proposal.collected_at) as collected_at,
  artifact.source_url,
  artifact.sha256 as artifact_sha256,
  amendment.payload_sha256
from territory.latest_transferegov_historical_amendments as amendment
join territory.federal_transfer_proposals as proposal
  on proposal.proposal_id = amendment.payload ->> 'id_proposta'
join raw.raw_artifacts as artifact
  on artifact.id = amendment.raw_artifact_id
where amendment.payload ->> 'id_proposta' ~ '^[0-9]+$'
  and nullif(btrim(amendment.payload ->> 'autor_nome'), '') is not null
  and amendment.payload ->> 'valor_repasse_emenda'
    ~ '^[0-9]{1,18}(?:[.][0-9]{1,2})?$'
  and (amendment.payload ->> 'valor_repasse_emenda')::numeric >= 0
  and artifact.source_url like 'https://%'
  and artifact.sha256 ~ '^[0-9a-f]{64}$';

revoke all on territory.latest_transferegov_historical_amendments from public;
revoke all on territory.latest_transferegov_historical_amendments
  from anon, authenticated;
revoke all on territory.historical_parliamentary_amendments from public;
revoke all on territory.historical_parliamentary_amendments
  from anon, authenticated;

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
        order by
          grouped.destination_amount desc,
          grouped.author_name
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

revoke all on function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
) from public;
revoke all on function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
) from public;

grant execute on function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
) to anon, authenticated;

comment on view territory.historical_parliamentary_amendments is
  'Emendas historicas ligadas a propostas de Barreiras, sem afirmar pagamento.';
comment on function api.get_public_historical_parliamentary_amendments(
  smallint, text, integer
) is
  'Emendas historicas sanitizadas com autoria, proposta, valor e evidencia.';
comment on function api.get_public_historical_parliamentary_amendment_ranking(
  text, smallint, integer
) is
  'Ranking historico separado da API corrente e sem nota subjetiva.';

notify pgrst, 'reload schema';

commit;
