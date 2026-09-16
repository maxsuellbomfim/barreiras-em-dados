begin;
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
  select * into outcome from procurement.normalize_pncp_contracts(500);
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
