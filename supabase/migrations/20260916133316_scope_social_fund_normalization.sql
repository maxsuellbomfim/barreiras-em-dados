begin;
-- Isolate the reviewed pair from the general pending queue. Existing global normalizer is unchanged.
create or replace function procurement.normalize_pncp_social_fund_pair(
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

  -- Primeiro normaliza as contratações-pai. DISTINCT ON evita criar versões
  -- repetidas quando o mesmo registro aparece em mais de uma página bruta.
  for v_record in
    select distinct on (rr.payload ->> 'numeroControlePNCP')
      rr.id,
      rr.payload,
      rr.payload_sha256
      from raw.raw_records as rr
     where rr.record_type = 'pncp_contratacao'
       and rr.payload->>'numeroControlePNCP'='13250888000162-1-000003/2026'
       and nullif(btrim(rr.payload ->> 'numeroControlePNCP'), '') is not null
       and procurement.pncp_owner_body(rr.payload #>> '{orgaoEntidade,cnpj}') is not null
     order by rr.payload ->> 'numeroControlePNCP', rr.collected_at desc, rr.created_at desc, rr.id desc
  loop
    v_external_id := nullif(btrim(v_record.payload ->> 'numeroControlePNCP'), '');
    v_body_id := procurement.pncp_owner_body(v_record.payload #>> '{orgaoEntidade,cnpj}');
    if v_external_id !~ '^[0-9]{14}-1-[0-9]{1,12}/[0-9]{4}$'
       or left(v_external_id,14) <> (v_record.payload #>> '{orgaoEntidade,cnpj}') then
      continue;
    end if;

    select p.id, p.public_body_id, p.origin_raw_record_id, p.version, origin.payload_sha256
      into v_existing
      from procurement.procurements as p
      join raw.raw_records as origin on origin.id = p.origin_raw_record_id
     where p.external_id = v_external_id
     order by p.version desc, p.created_at desc
     limit 1;

    if v_existing.id is not null
       and v_existing.payload_sha256 = v_record.payload_sha256
       and v_existing.public_body_id = v_body_id then
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
  -- Controles ausentes continuam diagnosticados, sem identidade inventada e
  -- sem consumir o lote de chaves válidas. A contagem também é limitada.
  select count(*)::integer into v_contracts_skipped
    from (
      select 1
        from raw.raw_records as rr
       where rr.record_type = 'pncp_contrato'
         and rr.payload->>'numeroControlePNCP'='13654405000195-2-000023/2026'
         and procurement.pncp_owner_body(rr.payload #>> '{orgaoEntidade,cnpj}') is not null
         and coalesce(
           nullif(btrim(rr.payload ->> 'numeroControlePNCP'), ''),
           nullif(btrim(rr.payload ->> 'numeroControlePncp'), '')
         ) is null
       limit v_limit
    ) as invalid_controls;

  for v_record in
    with candidates as (
      select rr.id, rr.payload, rr.payload_sha256,
             rr.collected_at, rr.created_at,
             coalesce(
               nullif(btrim(rr.payload ->> 'numeroControlePNCP'), ''),
               nullif(btrim(rr.payload ->> 'numeroControlePncp'), '')
             ) as external_id
        from raw.raw_records as rr
       where rr.record_type = 'pncp_contrato'
         and rr.payload->>'numeroControlePNCP'='13654405000195-2-000023/2026'
         and procurement.pncp_owner_body(rr.payload #>> '{orgaoEntidade,cnpj}') is not null
    ), latest as (
      -- As duas grafias oficiais e espaços laterais definem a mesma chave.
      -- Escolher antes do LIMIT impede restaurar uma observação histórica.
      select distinct on (candidate.external_id) candidate.*
        from candidates as candidate
       where candidate.external_id is not null
       order by candidate.external_id,
                candidate.collected_at desc, candidate.created_at desc, candidate.id desc
    )
    select snapshot.id, snapshot.payload, snapshot.payload_sha256
      from latest as snapshot
      left join lateral (
        select origin.payload_sha256, c.public_body_id, c.procurement_id
          from procurement.contracts as c
          join raw.raw_records as origin on origin.id = c.origin_raw_record_id
         where c.external_id = snapshot.external_id
         order by c.version desc, c.created_at desc, c.id desc
         limit 1
      ) as current_contract on true
     -- Ignorar a versão já normalizada antes do limite permite drenar outras
     -- chaves e evita repetir trabalho/versionamento de fornecedores.
     where snapshot.external_id ~ '^[0-9]{14}-2-[0-9]{1,12}/[0-9]{4}$'
       and left(snapshot.external_id,14)=(snapshot.payload #>> '{orgaoEntidade,cnpj}')
       and (current_contract.payload_sha256 is distinct from snapshot.payload_sha256
         or current_contract.public_body_id is distinct from
            procurement.pncp_owner_body(snapshot.payload #>> '{orgaoEntidade,cnpj}')
         or current_contract.procurement_id is distinct from
            procurement.pncp_parent_procurement(coalesce(
              nullif(btrim(snapshot.payload ->> 'numeroControlePncpCompra'),''),
              nullif(btrim(snapshot.payload ->> 'numeroControlePNCPCompra'),'')
            )))
     order by snapshot.collected_at desc, snapshot.created_at desc, snapshot.id desc
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

    v_body_id := procurement.pncp_owner_body(v_record.payload #>> '{orgaoEntidade,cnpj}');
    if nullif(btrim(v_record.payload ->> 'numeroControlePncpCompra'),'') is not null
       and nullif(btrim(v_record.payload ->> 'numeroControlePNCPCompra'),'') is not null
       and btrim(v_record.payload ->> 'numeroControlePncpCompra') <>
           btrim(v_record.payload ->> 'numeroControlePNCPCompra') then
      v_contracts_skipped := v_contracts_skipped + 1;
      continue;
    end if;
    v_procurement_id := procurement.pncp_parent_procurement(v_parent_external_id);

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

    select c.id, c.version, c.public_body_id, c.procurement_id, origin.payload_sha256
      into v_existing
      from procurement.contracts as c
      join raw.raw_records as origin on origin.id = c.origin_raw_record_id
     where c.external_id = v_external_id
     order by c.version desc, c.created_at desc
     limit 1;

    if v_existing.id is not null
       and v_existing.payload_sha256 = v_record.payload_sha256
       and v_existing.public_body_id = v_body_id
       and v_existing.procurement_id is not distinct from v_procurement_id then
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


revoke all on function procurement.normalize_pncp_social_fund_pair(integer) from public,anon,authenticated,collector_worker;

create or replace function procurement.publish_social_fund_pair(
  contract_artifact uuid, contract_bytes bytea, purchase_artifact uuid, purchase_bytes bytea
) returns jsonb language plpgsql security definer set search_path=pg_catalog as $publish$
declare
  keys text[]:=array['13654405000195-2-000023/2026','13250888000162-1-000003/2026'];
  owners text[]:=array['13654405000195','13250888000162'];
  urls text[]:=array['https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/contratos/2026/23',
    'https://pncp.gov.br/api/consulta/v1/orgaos/13250888000162/compras/2026/3'];
  ids uuid[]:=array[contract_artifact,purchase_artifact];
  bodies bytea[]:=array[contract_bytes,purchase_bytes];
  records uuid[]:=array[null::uuid,null::uuid];
  payloads jsonb[]:=array[null::jsonb,null::jsonb];
  kinds text[]:=array['pncp_contrato','pncp_contratacao'];
  a raw.raw_artifacts%rowtype;
  fund uuid;
  record_id uuid;
  owner_count integer;
  i integer;
  before_c integer;
  before_p integer;
  outcome record;
begin
  lock table raw.raw_records,org.public_bodies,procurement.procurements,
    procurement.contracts,procurement.suppliers in share row exclusive mode;
  for i in 1..2 loop
    if bodies[i] is null or octet_length(bodies[i]) not between 2 and 32768 then
      raise exception 'Tamanho inválido; publicação bloqueada';
    end if;
    select * into a from raw.raw_artifacts where id=ids[i];
    if not found then raise exception 'Artefato não preservado'; end if;
    if a.source_url is distinct from urls[i] or a.http_status is distinct from 200
      or a.metadata->>'schema_name' is distinct from 'pncp-registry-snapshot'
      or a.metadata->>'final_url' is distinct from urls[i]
      or a.byte_size is distinct from octet_length(bodies[i])::bigint
      or a.sha256 is distinct from encode(extensions.digest(bodies[i],'sha256'),'hex') then
      raise exception 'Artefato incompatível; publicação bloqueada';
    end if;
    payloads[i]:=convert_from(bodies[i],'UTF8')::jsonb;
    if jsonb_typeof(payloads[i]) is distinct from 'object'
      or payloads[i]->>'numeroControlePNCP' is distinct from keys[i]
      or payloads[i]#>>'{orgaoEntidade,cnpj}' is distinct from owners[i]
      or payloads[i]#>>'{unidadeOrgao,codigoIbge}' is distinct from '2903201' then
      raise exception 'Identidade incompatível; publicação bloqueada';
    end if;
    if exists(select 1 from raw.raw_records r where r.record_type=kinds[i]
      and r.payload->>'numeroControlePNCP'=keys[i] and r.payload<>payloads[i]) then
      raise exception 'Existe versão divergente; exige nova revisão';
    end if;
  end loop;
  if coalesce(payloads[1]->>'numeroControlePNCPCompra',payloads[1]->>'numeroControlePncpCompra') is distinct from keys[2]
    or (payloads[1] ? 'numeroControlePNCPCompra' and payloads[1]->>'numeroControlePNCPCompra' is distinct from keys[2])
    or (payloads[1] ? 'numeroControlePncpCompra' and payloads[1]->>'numeroControlePncpCompra' is distinct from keys[2])
    or (payloads[1]->>'valorGlobal')::numeric is distinct from 28780::numeric
    or coalesce(payloads[1]->>'valorAcumulado',payloads[1]->>'valorGlobal')::numeric is distinct from 28780::numeric
    or (payloads[2]->>'valorTotalEstimado')::numeric is distinct from 28780::numeric
    or nullif(btrim(payloads[2]#>>'{orgaoEntidade,razaoSocial}'),'') is null then
    raise exception 'Vínculo ou valores divergentes; publicação bloqueada';
  end if;
  select count(*) into before_c from procurement.contracts where external_id=keys[1];
  select count(*) into before_p from procurement.procurements where external_id=keys[2];
  for i in 1..2 loop
    select id into record_id from raw.raw_records where record_type=kinds[i]
      and payload=payloads[i] order by collected_at desc,created_at desc,id desc limit 1;
    if record_id is null then
      select * into a from raw.raw_artifacts where id=ids[i];
      insert into raw.raw_records(raw_artifact_id,source_record_key,record_type,record_index,
        payload,payload_sha256,parser_version,idempotency_key,collected_at)
      values(ids[i],keys[i],kinds[i],0,payloads[i],
        encode(extensions.digest(convert_to(payloads[i]::text,'UTF8'),'sha256'),'hex'),
        'pncp-reviewed-social-fund/1.0.0','pncp-reviewed-social-fund:'||a.sha256,a.retrieved_at)
      returning id into record_id;
    end if;
    records[i]:=record_id;
  end loop;
  select count(*),(array_agg(id))[1] into owner_count,fund from org.public_bodies
    where regexp_replace(official_code,'[^0-9]','','g')=owners[2] and active_until is null;
  if owner_count>1 then raise exception 'Órgão ambíguo'; end if;
  if owner_count=0 then
    insert into org.public_bodies(origin_raw_record_id,ibge_code,official_code,name,body_type,jurisdiction,state_code)
    values(records[2],'2903201',owners[2],payloads[2]#>>'{orgaoEntidade,razaoSocial}','municipal_fund','municipal','BA')
    returning id into fund;
  elsif not exists(select 1 from org.public_bodies where id=fund and ibge_code='2903201'
    and body_type='municipal_fund' and name=payloads[2]#>>'{orgaoEntidade,razaoSocial}') then
    raise exception 'Cadastro do Fundo incompatível';
  end if;
  select * into outcome from procurement.normalize_pncp_social_fund_pair(500);
  if outcome.procurements_inserted<>(case when before_p=0 then 1 else 0 end)
    or outcome.contracts_inserted<>(case when before_c=0 then 1 else 0 end)
    or outcome.suppliers_inserted>1 then
    raise exception 'Normalização excedeu o lote autorizado; operação revertida';
  end if;
  if not exists(select 1 from procurement.contracts c join procurement.procurements p on p.id=c.procurement_id
    where c.external_id=keys[1] and p.external_id=keys[2]
      and c.origin_raw_record_id=records[1] and p.origin_raw_record_id=records[2]
      and c.public_body_id=procurement.pncp_owner_body(owners[1]) and p.public_body_id=fund
      and c.current_amount=28780) then
    raise exception 'Vínculo final não validado; operação revertida';
  end if;
  return jsonb_build_object('contracts',1,'procurements',1,'status','published');
end;
$publish$;
revoke all on function procurement.publish_social_fund_pair(uuid,bytea,uuid,bytea) from public,anon,authenticated;
grant execute on function procurement.publish_social_fund_pair(uuid,bytea,uuid,bytea) to collector_worker;

commit;
