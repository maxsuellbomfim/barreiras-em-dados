begin;

-- Fundos são identificados separadamente, sem classificá-los como Prefeitura
-- ou presumir personalidade jurídica/autonomia administrativa.
alter table org.public_bodies drop constraint public_bodies_body_type_check;
alter table org.public_bodies add constraint public_bodies_body_type_check check (
  body_type in ('executive','legislative','indirect_administration','oversight','other','municipal_fund')
);
drop index org.public_bodies_ibge_active_idx;
create unique index public_bodies_ibge_active_idx
  on org.public_bodies(ibge_code,body_type)
  where ibge_code is not null and active_until is null and body_type <> 'municipal_fund';
create unique index if not exists public_bodies_fund_cnpj_active_idx
  on org.public_bodies(ibge_code,official_code)
  where body_type='municipal_fund' and active_until is null;
alter table org.public_bodies drop constraint if exists public_bodies_fund_identity_check;
alter table org.public_bodies add constraint public_bodies_fund_identity_check check (
  body_type <> 'municipal_fund' or
  (ibge_code is not null and official_code is not null and official_code ~ '^[0-9]{14}$')
);

-- Operação explícita: migrations de uma instalação vazia não exigem dados de produção.
create or replace function procurement.repair_reviewed_fund_owners()
returns integer language plpgsql security definer set search_path=pg_catalog as $repair$
declare
  target record;
  current_contract procurement.contracts%rowtype;
  evidence record;
  fund_id uuid;
  matches integer;
  repaired integer := 0;
begin
  lock table org.public_bodies, procurement.contracts, finance.commitments,
    procurement.contract_amendments, procurement.public_works in share row exclusive mode;
  for target in select * from (values
    ('30667266000153','30667266000153-2-000013/2026','FUNDO MUNICIPAL DE EDUCACAO FMED',
     '5117962643d65c60aba9bcb72449ab4b13f44bb9b5edc633fa9f3d5028ebcdbf',30756.96::numeric),
    ('50525166000108','50525166000108-2-000062/2026','FUNDO MUNICIPAL DE CULTURA DE BARREIRAS - FMCB',
     '29b00d5f75451024ccea89093ffe1b46684ad2c719d938f50c0804044ee388e2',11259.12::numeric)
  ) as reviewed(cnpj,control,name,payload_hash,amount)
  loop
    select * into current_contract from procurement.contracts
    where external_id=target.control order by version desc,created_at desc,id desc limit 1;
    if not found then raise exception 'Contrato revisado ausente; reparo bloqueado'; end if;

    select r.payload,r.payload_sha256,r.record_type,a.sha256,a.http_status,a.byte_size,a.source_url
    into evidence from raw.raw_records r join raw.raw_artifacts a on a.id=r.raw_artifact_id
    where r.id=current_contract.origin_raw_record_id;
    if not found then raise exception 'Evidência preservada ausente; reparo bloqueado'; end if;
    if evidence.payload_sha256 is distinct from target.payload_hash
      or evidence.record_type is distinct from 'pncp_contrato'
      or evidence.payload->>'numeroControlePNCP' is distinct from target.control
      or evidence.payload#>>'{orgaoEntidade,cnpj}' is distinct from target.cnpj
      or evidence.payload#>>'{orgaoEntidade,razaoSocial}' is distinct from target.name
      or evidence.payload#>>'{unidadeOrgao,codigoIbge}' is distinct from '2903201'
      or coalesce(evidence.payload->>'numeroControlePNCPCompra',evidence.payload->>'numeroControlePncpCompra')
         is distinct from '13654405000195-1-000002/2026'
      or evidence.sha256 is distinct from 'c5bea3b7b0c28a793d139dcd577d62c2250654215076910b53a778096f2ca2f9'
      or evidence.http_status is distinct from 200 or evidence.byte_size is distinct from 5931
      or evidence.source_url is distinct from 'https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/contratos/contratacao/2026/2?pagina=1&tamanhoPagina=50'
      or current_contract.current_amount is distinct from target.amount
      or not exists(select 1 from procurement.procurements p where p.id=current_contract.procurement_id
                    and p.external_id='13654405000195-1-000002/2026') then
      raise exception 'Evidência diverge do lote revisado; reparo bloqueado';
    end if;

    select count(*),(array_agg(id))[1] into matches,fund_id from org.public_bodies
    where regexp_replace(official_code,'[^0-9]','','g')=target.cnpj and active_until is null;
    if matches>1 then raise exception 'Cadastro ambíguo; reparo bloqueado'; end if;
    if matches=0 then
      insert into org.public_bodies(origin_raw_record_id,ibge_code,official_code,name,body_type,jurisdiction,state_code)
      values(current_contract.origin_raw_record_id,'2903201',target.cnpj,target.name,'municipal_fund','municipal','BA')
      returning id into fund_id;
    elsif not exists(select 1 from org.public_bodies where id=fund_id and ibge_code='2903201'
                     and body_type='municipal_fund' and name=target.name) then
      raise exception 'Cadastro incompatível; reparo bloqueado';
    end if;
    if current_contract.public_body_id=fund_id then continue; end if;
    if not exists(select 1 from org.public_bodies where id=current_contract.public_body_id
                  and official_code='PREF-BARREIRAS' and body_type='executive' and ibge_code='2903201') then
      raise exception 'Órgão anterior diverge do lote revisado; reparo bloqueado';
    end if;
    -- Não deixar vínculos dependentes apontando exclusivamente à versão antiga.
    if exists(select 1 from finance.commitments where contract_id=current_contract.id)
       or exists(select 1 from procurement.contract_amendments where contract_id=current_contract.id)
       or exists(select 1 from procurement.public_works where contract_id=current_contract.id) then
      raise exception 'Contrato possui vínculos dependentes; exige revisão específica';
    end if;

    insert into procurement.contracts(origin_raw_record_id,public_body_id,procurement_id,supplier_id,
      supersedes_id,version,external_id,contract_number,object_description,signed_date,effective_from,
      effective_until,initial_amount,current_amount,currency,status)
    values(current_contract.origin_raw_record_id,fund_id,current_contract.procurement_id,current_contract.supplier_id,
      current_contract.id,current_contract.version+1,current_contract.external_id,current_contract.contract_number,
      current_contract.object_description,current_contract.signed_date,current_contract.effective_from,
      current_contract.effective_until,current_contract.initial_amount,current_contract.current_amount,
      current_contract.currency,current_contract.status);
    repaired := repaired + 1;
  end loop;
  return repaired;
end;
$repair$;
revoke all on function procurement.repair_reviewed_fund_owners() from public;
commit;
