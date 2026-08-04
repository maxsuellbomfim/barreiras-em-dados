begin;

-- Converte somente fatos já preservados pelo coletor PNCP. A rotina não cria
-- empenhos: o endpoint de contratos informa número/valor do contrato, mas não
-- prova que esse número seja um empenho contábil. O vínculo financeiro será
-- criado quando a fonte de execução trouxer o identificador oficial.
create index if not exists suppliers_registration_version_idx
  on procurement.suppliers (public_registration_number, version desc)
  where public_registration_number is not null;

create index if not exists procurements_external_version_lookup_idx
  on procurement.procurements (public_body_id, external_id, version desc)
  where external_id is not null;

create index if not exists contracts_external_version_lookup_idx
  on procurement.contracts (public_body_id, external_id, version desc)
  where external_id is not null;

create or replace function procurement.normalize_pncp_contracts(
  p_limit integer default 500
)
returns table (
  procurements_inserted integer,
  suppliers_inserted integer,
  contracts_inserted integer,
  contracts_skipped integer
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_body_id uuid;
  v_body_cnpj text;
  v_record record;
  v_existing record;
  v_procurement_id uuid;
  v_supplier_id uuid;
  v_external_id text;
  v_parent_external_id text;
  v_registration text;
  v_supplier_name text;
  v_supplier_normalized_name text;
  v_procurement_inserted integer := 0;
  v_suppliers_inserted integer := 0;
  v_contracts_inserted integer := 0;
  v_contracts_skipped integer := 0;
  v_limit integer;
begin
  v_limit := least(greatest(coalesce(p_limit, 500), 1), 5000);

  select body.id, coalesce(
      nullif(regexp_replace(body.official_code, '[^0-9]', '', 'g'), ''),
      '13654405000195'
    )
    into v_body_id, v_body_cnpj
    from org.public_bodies as body
   where body.ibge_code = '2903201'
     and body.body_type = 'executive'
   order by body.active_until nulls first, body.version desc
   limit 1;

  if v_body_id is null then
    raise exception 'Órgão executivo de Barreiras não está normalizado';
  end if;

  -- Primeiro normaliza as contratações-pai. DISTINCT ON evita criar versões
  -- repetidas quando o mesmo registro aparece em mais de uma página bruta.
  for v_record in
    select distinct on (rr.payload ->> 'numeroControlePNCP')
      rr.id,
      rr.payload,
      rr.payload_sha256
      from raw.raw_records as rr
     where rr.record_type = 'pncp_contratacao'
       and nullif(btrim(rr.payload ->> 'numeroControlePNCP'), '') is not null
       and (
         rr.payload #>> '{orgaoEntidade,cnpj}' = v_body_cnpj
         or rr.payload #>> '{unidadeOrgao,codigoIbge}' = '2903201'
       )
     order by rr.payload ->> 'numeroControlePNCP', rr.collected_at desc, rr.created_at desc
  loop
    v_external_id := nullif(btrim(v_record.payload ->> 'numeroControlePNCP'), '');

    select p.id, p.origin_raw_record_id, p.version, origin.payload_sha256
      into v_existing
      from procurement.procurements as p
      join raw.raw_records as origin on origin.id = p.origin_raw_record_id
     where p.public_body_id = v_body_id
       and p.external_id = v_external_id
     order by p.version desc, p.created_at desc
     limit 1;

    if v_existing.id is not null
       and v_existing.payload_sha256 = v_record.payload_sha256 then
      continue;
    end if;

    insert into procurement.procurements (
      origin_raw_record_id,
      public_body_id,
      supersedes_id,
      version,
      external_id,
      process_number,
      procurement_mode,
      object_description,
      legal_basis,
      status,
      publication_date,
      opening_date,
      estimated_amount,
      awarded_amount
    )
    values (
      v_record.id,
      v_body_id,
      v_existing.id,
      coalesce(v_existing.version, 0) + 1,
      v_external_id,
      nullif(btrim(v_record.payload ->> 'processo'), ''),
      nullif(btrim(v_record.payload ->> 'modalidadeNome'), ''),
      coalesce(nullif(btrim(v_record.payload ->> 'objetoCompra'), ''), 'Objeto não informado no registro do PNCP'),
      nullif(btrim(v_record.payload #>> '{amparoLegal,nome}'), ''),
      nullif(btrim(v_record.payload ->> 'situacaoCompraNome'), ''),
      case
        when left(v_record.payload ->> 'dataPublicacaoPncp', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then left(v_record.payload ->> 'dataPublicacaoPncp', 10)::date
      end,
      case
        when v_record.payload ->> 'dataAberturaProposta' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        then (v_record.payload ->> 'dataAberturaProposta')::timestamptz
      end,
      case
        when v_record.payload ->> 'valorTotalEstimado' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'valorTotalEstimado')::numeric
      end,
      case
        when v_record.payload ->> 'valorTotalHomologado' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'valorTotalHomologado')::numeric
      end
    )
    returning id into v_procurement_id;
    v_procurement_inserted := v_procurement_inserted + 1;
  end loop;

  -- Contratos são a unidade pública que o endpoint efetivamente entrega.
  -- Registros sem controle PNCP não são publicados como contratos normalizados.
  for v_record in
    select rr.id, rr.payload, rr.payload_sha256
      from raw.raw_records as rr
     where rr.record_type = 'pncp_contrato'
       and (
         rr.payload #>> '{orgaoEntidade,cnpj}' = v_body_cnpj
         or rr.payload #>> '{unidadeOrgao,codigoIbge}' = '2903201'
       )
     order by rr.collected_at desc, rr.created_at desc
     limit v_limit
  loop
    v_external_id := coalesce(
      nullif(btrim(v_record.payload ->> 'numeroControlePNCP'), ''),
      nullif(btrim(v_record.payload ->> 'numeroControlePncp'), '')
    );
    v_parent_external_id := coalesce(
      nullif(btrim(v_record.payload ->> 'numeroControlePncpCompra'), ''),
      nullif(btrim(v_record.payload ->> 'numeroControlePNCPCompra'), '')
    );

    if v_external_id is null then
      v_contracts_skipped := v_contracts_skipped + 1;
      continue;
    end if;

    select p.id into v_procurement_id
      from procurement.procurements as p
     where p.public_body_id = v_body_id
       and p.external_id = v_parent_external_id
     order by p.version desc, p.created_at desc
     limit 1;

    v_registration := regexp_replace(coalesce(v_record.payload ->> 'niFornecedor', ''), '[^0-9]', '', 'g');
    v_supplier_name := coalesce(
      nullif(btrim(v_record.payload ->> 'nomeRazaoSocialFornecedor'), ''),
      nullif(btrim(v_record.payload ->> 'usuarioNome'), ''),
      'Fornecedor não informado'
    );
    v_supplier_normalized_name := upper(regexp_replace(btrim(v_supplier_name), '\s+', ' ', 'g'));
    v_supplier_id := null;

    if length(v_registration) = 14
       and upper(coalesce(v_record.payload ->> 'tipoPessoa', 'PJ')) <> 'PF' then
      select s.id, s.version, s.normalized_name, origin.payload_sha256
        into v_existing
        from procurement.suppliers as s
        join raw.raw_records as origin on origin.id = s.origin_raw_record_id
       where s.public_registration_number = v_registration
       order by s.version desc, s.created_at desc
       limit 1;

      if v_existing.id is not null
         and v_existing.normalized_name = v_supplier_normalized_name then
        v_supplier_id := v_existing.id;
      else
        insert into procurement.suppliers (
          origin_raw_record_id,
          supersedes_id,
          version,
          entity_type,
          legal_name,
          normalized_name,
          public_registration_type,
          public_registration_number,
          municipality,
          state_code
        )
        values (
          v_record.id,
          v_existing.id,
          coalesce(v_existing.version, 0) + 1,
          case when upper(v_record.payload ->> 'tipoPessoa') = 'PF' then 'natural_person' else 'legal_entity' end,
          v_supplier_name,
          v_supplier_normalized_name,
          'CNPJ',
          v_registration,
          nullif(btrim(v_record.payload #>> '{unidadeOrgao,municipioNome}'), ''),
          nullif(upper(btrim(v_record.payload #>> '{unidadeOrgao,ufSigla}')), '')
        )
        returning id into v_supplier_id;
        v_suppliers_inserted := v_suppliers_inserted + 1;
      end if;
    end if;

    select c.id, c.version, origin.payload_sha256
      into v_existing
      from procurement.contracts as c
      join raw.raw_records as origin on origin.id = c.origin_raw_record_id
     where c.public_body_id = v_body_id
       and c.external_id = v_external_id
     order by c.version desc, c.created_at desc
     limit 1;

    if v_existing.id is not null
       and v_existing.payload_sha256 = v_record.payload_sha256 then
      continue;
    end if;

    insert into procurement.contracts (
      origin_raw_record_id,
      public_body_id,
      procurement_id,
      supplier_id,
      supersedes_id,
      version,
      external_id,
      contract_number,
      object_description,
      signed_date,
      effective_from,
      effective_until,
      initial_amount,
      current_amount,
      status
    )
    values (
      v_record.id,
      v_body_id,
      v_procurement_id,
      v_supplier_id,
      v_existing.id,
      coalesce(v_existing.version, 0) + 1,
      v_external_id,
      nullif(btrim(v_record.payload ->> 'numeroContratoEmpenho'), ''),
      coalesce(nullif(btrim(v_record.payload ->> 'objetoContrato'), ''), 'Objeto não informado no registro do contrato'),
      case
        when left(v_record.payload ->> 'dataAssinatura', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then left(v_record.payload ->> 'dataAssinatura', 10)::date
      end,
      case
        when left(v_record.payload ->> 'dataVigenciaInicio', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then left(v_record.payload ->> 'dataVigenciaInicio', 10)::date
      end,
      case
        when left(v_record.payload ->> 'dataVigenciaFim', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then left(v_record.payload ->> 'dataVigenciaFim', 10)::date
      end,
      case
        when v_record.payload ->> 'valorInicial' ~ '^[0-9]+(\.[0-9]+)?$'
        then (v_record.payload ->> 'valorInicial')::numeric
      end,
      case
        when coalesce(v_record.payload ->> 'valorAcumulado', v_record.payload ->> 'valorGlobal') ~ '^[0-9]+(\.[0-9]+)?$'
        then coalesce(v_record.payload ->> 'valorAcumulado', v_record.payload ->> 'valorGlobal')::numeric
      end,
      nullif(btrim(v_record.payload ->> 'situacaoContrato'), '')
    );
    v_contracts_inserted := v_contracts_inserted + 1;
  end loop;

  return query select
    v_procurement_inserted,
    v_suppliers_inserted,
    v_contracts_inserted,
    v_contracts_skipped;
end;
$$;

comment on function procurement.normalize_pncp_contracts(integer) is
  'Normaliza contratos PNCP preservados, mantendo origem e versões. Não cria empenhos sem identificador contábil oficial.';

revoke all on function procurement.normalize_pncp_contracts(integer) from public, anon, authenticated;
grant usage on schema procurement to collector_worker;
grant execute on function procurement.normalize_pncp_contracts(integer) to collector_worker;

commit;
