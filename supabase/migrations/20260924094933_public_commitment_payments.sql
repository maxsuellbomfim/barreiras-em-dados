begin;

-- ADR 0087. Pagamentos dos empenhos exibidos em cada contrato municipal. A
-- ligação pagamento -> empenho é a CHAVE oficial que a própria fonte publica
-- em cada pagamento; não há inferência. A busca parte das chaves pedidas e só
-- depois restringe à grade mais recente de cada mês (mesma lição da RPC de
-- liquidações). Valores ficam como texto literal e nada é somado.
create index raw_records_municipal_payment_key_idx
  on raw.raw_records ((payload ->> 'field1082596'), raw_artifact_id)
  where record_type = 'municipal_payment_webrun';

create index raw_artifacts_payment_grid_month_idx
  on raw.raw_artifacts (
    (metadata -> 'cursor' ->> 'month'),
    retrieved_at desc,
    id desc
  )
  where metadata ->> 'schema_name' = 'municipal-payments-webrun-grid';

create function api.get_public_commitment_payments(
  commitment_keys text[]
)
returns table (
  commitment_key text,
  payment_id text,
  payment_date_text text,
  amount_text text,
  process_number text,
  contract_text text,
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
    where record.record_type = 'municipal_payment_webrun'
      and record.payload ->> 'field1082596' = any(commitment_keys)
      and record.payload ->> 'field1082596' ~ '^O-[0-9]+$'
  ),
  latest_grids as (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id,
      artifact.sha256,
      artifact.metadata -> 'cursor' ->> 'month' as grid_month
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  )
  select
    candidate.payload ->> 'field1082596',
    candidate.payload ->> 'field1082593',
    candidate.payload ->> 'field1082587',
    candidate.payload ->> 'field1082592',
    nullif(btrim(candidate.payload ->> 'field1082597'), ''),
    nullif(btrim(candidate.payload ->> 'field1144926'), ''),
    grid.sha256,
    grid.grid_month,
    'commitment-payments/1.0.0'::text
  from candidates as candidate
  join latest_grids as grid
    on grid.id = candidate.raw_artifact_id
  order by
    candidate.payload ->> 'field1082596',
    to_date(candidate.payload ->> 'field1082587', 'DD/MM/YYYY'),
    candidate.record_index
  limit 5000;
end;
$function$;

revoke all on function api.get_public_commitment_payments(text[]) from public;
grant execute on function api.get_public_commitment_payments(text[])
  to anon, authenticated;

comment on function api.get_public_commitment_payments(text[]) is
  'Pagamentos por chave oficial de empenho (ADR 0087): grade mais recente de cada mês, valores em texto da fonte, sem somas.';

commit;
