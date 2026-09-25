begin;

-- ADR 0087. Liquidações dos empenhos exibidos em cada contrato municipal.
-- A ligação liquidação -> empenho é a CHAVE oficial publicada pela própria
-- fonte em cada linha; não há regra de inferência. Só entra a grade mais
-- recente de cada mês (uma correção da fonte substitui, sem somar, a leitura
-- anterior); valores ficam como texto literal e nada é somado.
create index raw_records_municipal_liquidation_key_idx
  on raw.raw_records ((payload ->> 'field1089487'), raw_artifact_id)
  where record_type = 'municipal_liquidation_webrun';

create function api.get_public_commitment_liquidations(
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
  with latest_grids as (
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
    record.payload ->> 'field1089487',
    record.payload ->> 'field1089483',
    record.payload ->> 'field1089488',
    grid.sha256,
    grid.grid_month,
    'commitment-liquidations/1.0.0'::text
  from latest_grids as grid
  join raw.raw_records as record
    on record.raw_artifact_id = grid.id
   and record.record_type = 'municipal_liquidation_webrun'
  where record.payload ->> 'field1089487' = any(commitment_keys)
    and record.payload ->> 'field1089487' ~ '^O-[0-9]+$'
  order by
    record.payload ->> 'field1089487',
    to_date(record.payload ->> 'field1089483', 'DD/MM/YYYY'),
    record.record_index
  limit 5000;
end;
$function$;

revoke all on function api.get_public_commitment_liquidations(text[]) from public;
grant execute on function api.get_public_commitment_liquidations(text[])
  to anon, authenticated;

comment on function api.get_public_commitment_liquidations(text[]) is
  'Liquidações por chave oficial de empenho (ADR 0087): grade mais recente de cada mês, valores em texto da fonte, sem somas.';

commit;
