begin;

-- Propostas historicas do Transferegov sao publicadas em uma projecao propria.
-- Uma proposta cadastrada nao e tratada como emenda, transferencia ou pagamento,
-- pois o arquivo siconv_proposta nao informa autoria parlamentar nem comprova os
-- estagios financeiros posteriores.

create index if not exists raw_records_transferegov_historical_proposal_idx
  on raw.raw_records (
    source_record_key,
    collected_at desc,
    id desc
  )
  where record_type = 'transferegov_historical_proposal'
    and source_record_key is not null;

create view territory.latest_transferegov_historical_proposals
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
where record.record_type = 'transferegov_historical_proposal'
  and record.source_record_key is not null
order by
  record.source_record_key,
  record.collected_at desc,
  record.id desc;

create view territory.federal_transfer_proposals
with (security_barrier = true)
as
select
  latest.raw_record_id,
  latest.raw_artifact_id,
  latest.payload ->> 'id_proposta' as proposal_id,
  nullif(btrim(latest.payload ->> 'numero_proposta'), '') as proposal_number,
  (latest.payload ->> 'ano_proposta')::smallint as fiscal_year,
  nullif(btrim(latest.payload ->> 'data_proposta'), '') as proposal_date_text,
  nullif(btrim(latest.payload ->> 'situacao_proposta'), '') as proposal_status,
  nullif(btrim(latest.payload ->> 'situacao_projeto_basico'), '')
    as basic_project_status,
  nullif(btrim(latest.payload ->> 'modalidade'), '') as modality,
  nullif(btrim(latest.payload ->> 'objeto'), '') as object_description,
  nullif(btrim(latest.payload ->> 'item_investimento'), '') as investment_item,
  nullif(btrim(latest.payload ->> 'proponente'), '') as proponent_name,
  nullif(btrim(latest.payload ->> 'orgao'), '') as federal_body_name,
  nullif(btrim(latest.payload ->> 'orgao_superior'), '')
    as superior_federal_body_name,
  case
    when latest.payload ->> 'valor_global'
      ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    then (latest.payload ->> 'valor_global')::numeric(20,2)
  end as global_amount,
  case
    when latest.payload ->> 'valor_repasse'
      ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    then (latest.payload ->> 'valor_repasse')::numeric(20,2)
  end as requested_transfer_amount,
  case
    when latest.payload ->> 'valor_contrapartida'
      ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    then (latest.payload ->> 'valor_contrapartida')::numeric(20,2)
  end as counterpart_amount,
  'not_available_in_proposal_source'::text as authorship_status,
  'proposal_registered'::text as financial_stage,
  latest.collected_at,
  artifact.source_url,
  artifact.sha256 as artifact_sha256,
  latest.payload_sha256
from territory.latest_transferegov_historical_proposals as latest
join raw.raw_artifacts as artifact on artifact.id = latest.raw_artifact_id
where latest.payload ->> 'id_proposta' ~ '^[0-9]+$'
  and latest.payload ->> 'ano_proposta' ~ '^[0-9]{4}$'
  and (latest.payload ->> 'ano_proposta')::integer between 2021 and extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::integer
  and latest.payload ->> 'cod_municipio_ibge' = '2903201'
  and lower(btrim(latest.payload ->> 'municipio_proponente')) = 'barreiras'
  and artifact.source_url like 'https://%'
  and artifact.sha256 ~ '^[0-9a-f]{64}$';

revoke all on territory.latest_transferegov_historical_proposals from public;
revoke all on territory.latest_transferegov_historical_proposals
  from anon, authenticated;
revoke all on territory.federal_transfer_proposals from public;
revoke all on territory.federal_transfer_proposals from anon, authenticated;

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
    'federal-transfer-proposals/1.0.0'::text as methodology_version
  from territory.federal_transfer_proposals as proposal
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

revoke all on function api.get_public_federal_transfer_proposals(
  smallint,
  text,
  integer
) from public;
grant execute on function api.get_public_federal_transfer_proposals(
  smallint,
  text,
  integer
) to anon, authenticated;

comment on view territory.federal_transfer_proposals is
  'Propostas federais historicas de Barreiras; nao comprova autoria, transferencia ou pagamento.';
comment on function api.get_public_federal_transfer_proposals(
  smallint,
  text,
  integer
) is
  'Catalogo publico sanitizado de propostas federais; cada linha permanece ligada ao ZIP oficial preservado.';

notify pgrst, 'reload schema';

commit;
