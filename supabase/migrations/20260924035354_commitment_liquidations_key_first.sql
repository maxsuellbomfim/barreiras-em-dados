begin;

-- Depois da coleta de 2024 a 2026 (32 grades de liquidação), o plano que
-- partia das grades lia o payload de todas as ~53 mil liquidações para
-- filtrar pela chave: 3,2 s com cache frio, acima do timeout de 3 s do papel
-- anon. A busca agora parte das chaves pedidas (índice
-- raw_records_municipal_liquidation_key_idx) e só depois restringe à grade
-- mais recente de cada mês. Mesmo resultado, mesma assinatura.
create or replace function api.get_public_commitment_liquidations(
  commitment_keys text[]
)
returns table (
  commitment_key text,
  liquidation_date_text text,
  amount_text text,
  grid_artifact_sha256 text,
  grid_month text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if commitment_keys is null
     or cardinality(commitment_keys) < 1
     or cardinality(commitment_keys) > 500 then
    raise exception 'commitment_keys deve ter entre 1 e 500 chaves'
      using errcode = '22023';
  end if;

  return query
  with candidates as materialized (
    select
      record.raw_artifact_id,
      record.payload,
      record.record_index
    from raw.raw_records as record
    where record.record_type = 'municipal_liquidation_webrun'
      and record.payload ->> 'field1089487' = any(commitment_keys)
      and record.payload ->> 'field1089487' ~ '^O-[0-9]+$'
  ),
  latest_grids as (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id,
      artifact.sha256,
      artifact.metadata -> 'cursor' ->> 'month' as grid_month
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-liquidations-webrun-grid'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  )
  select
    candidate.payload ->> 'field1089487',
    candidate.payload ->> 'field1089483',
    candidate.payload ->> 'field1089488',
    grid.sha256,
    grid.grid_month,
    'commitment-liquidations/1.0.0'::text
  from candidates as candidate
  join latest_grids as grid
    on grid.id = candidate.raw_artifact_id
  order by
    candidate.payload ->> 'field1089487',
    to_date(candidate.payload ->> 'field1089483', 'DD/MM/YYYY'),
    candidate.record_index
  limit 5000;
end;
$function$;

commit;
