begin;

-- Materializa os itens já preservados pelo coletor. O vínculo com a contratação
-- vem exclusivamente da chave oficial pncp:item:<numeroControlePNCP>:<item>;
-- não há associação por nome, descrição ou proximidade de valores.
create index if not exists procurement_items_external_version_lookup_idx
  on procurement.procurement_items (procurement_id, external_item_number, version desc);

create or replace function procurement.normalize_pncp_items(
  p_limit integer default 500
)
returns table (
  items_inserted integer,
  items_skipped integer
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_record record;
  v_existing record;
  v_procurement_id uuid;
  v_parent_external_id text;
  v_item_number text;
  v_description text;
  v_inserted integer := 0;
  v_skipped integer := 0;
  v_limit integer;
begin
  v_limit := least(greatest(coalesce(p_limit, 500), 1), 5000);

  for v_record in
    with candidates as (
      select distinct on (rr.source_record_key)
        rr.id,
        rr.source_record_key,
        rr.payload,
        rr.payload_sha256,
        rr.collected_at,
        rr.created_at
        from raw.raw_records as rr
       where rr.record_type = 'pncp_item'
         and rr.source_record_key like 'pncp:item:%:%'
       order by rr.source_record_key, rr.collected_at desc, rr.created_at desc
    )
    select c.id, c.source_record_key, c.payload, c.payload_sha256
      from candidates as c
     where not exists (
       select 1
         from procurement.procurement_items as existing_item
         join procurement.procurements as existing_procurement
           on existing_procurement.id = existing_item.procurement_id
         join raw.raw_records as existing_origin
           on existing_origin.id = existing_item.origin_raw_record_id
        where existing_procurement.external_id = substring(
                c.source_record_key from '^pncp:item:([^:]+):'
              )
          and existing_item.external_item_number = nullif(
                btrim(c.payload ->> 'numeroItem'), ''
              )
          and existing_origin.payload_sha256 = c.payload_sha256
     )
     order by c.collected_at desc, c.created_at desc, c.source_record_key
     limit v_limit
  loop
    v_parent_external_id := substring(
      v_record.source_record_key from '^pncp:item:([^:]+):'
    );
    v_item_number := nullif(btrim(v_record.payload ->> 'numeroItem'), '');
    v_description := coalesce(
      nullif(btrim(v_record.payload ->> 'descricao'), ''),
      'Descrição não informada no registro do PNCP'
    );

    if v_parent_external_id is null or v_item_number is null then
      v_skipped := v_skipped + 1;
      continue;
    end if;

    select p.id
      into v_procurement_id
      from procurement.procurements as p
     where p.external_id = v_parent_external_id
     order by p.version desc, p.created_at desc
     limit 1;

    if v_procurement_id is null then
      v_skipped := v_skipped + 1;
      continue;
    end if;

    select i.id, i.version, origin.payload_sha256
      into v_existing
      from procurement.procurement_items as i
      join raw.raw_records as origin on origin.id = i.origin_raw_record_id
     where i.procurement_id = v_procurement_id
       and i.external_item_number = v_item_number
     order by i.version desc, i.created_at desc
     limit 1;

    if v_existing.id is not null
       and v_existing.payload_sha256 = v_record.payload_sha256 then
      v_skipped := v_skipped + 1;
      continue;
    end if;

    insert into procurement.procurement_items (
      origin_raw_record_id,
      procurement_id,
      supersedes_id,
      version,
      external_item_number,
      description,
      normalized_description,
      catalog_code,
      quantity,
      unit_name,
      estimated_unit_amount,
      estimated_total_amount,
      result_status
    )
    values (
      v_record.id,
      v_procurement_id,
      v_existing.id,
      coalesce(v_existing.version, 0) + 1,
      v_item_number,
      v_description,
      upper(regexp_replace(btrim(v_description), '\s+', ' ', 'g')),
      coalesce(
        nullif(btrim(v_record.payload ->> 'catalogoCodigoItem'), ''),
        nullif(btrim(v_record.payload ->> 'ncmNbsCodigo'), '')
      ),
      case
        when v_record.payload ->> 'quantidade' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'quantidade')::numeric
      end,
      nullif(btrim(v_record.payload ->> 'unidadeMedida'), ''),
      case
        when v_record.payload ->> 'valorUnitarioEstimado' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'valorUnitarioEstimado')::numeric
      end,
      case
        when v_record.payload ->> 'valorTotal' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'valorTotal')::numeric
      end,
      nullif(btrim(v_record.payload ->> 'situacaoCompraItemNome'), '')
    );
    v_inserted := v_inserted + 1;
  end loop;

  return query select v_inserted, v_skipped;
end;
$$;

comment on function procurement.normalize_pncp_items(integer) is
  'Normaliza itens PNCP preservados usando somente a chave oficial da contratação.';

revoke all on function procurement.normalize_pncp_items(integer) from public, anon, authenticated;
grant usage on schema procurement to collector_worker;
grant execute on function procurement.normalize_pncp_items(integer) to collector_worker;

commit;
