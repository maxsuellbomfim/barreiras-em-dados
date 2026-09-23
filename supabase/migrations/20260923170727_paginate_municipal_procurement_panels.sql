begin;

-- Paginação no servidor para os painéis municipais de /licitacoes, que
-- enviavam 100 cartões cada dentro de seções fechadas. O corpo das funções é
-- o mesmo das migrations 20260818182729 e 20260819053000; o novo parâmetro
-- page_offset tem padrão 0, então as chamadas existentes devolvem o mesmo
-- resultado. A troca de assinatura exige drop/create para não deixar
-- sobrecargas ambíguas no PostgREST.

drop function if exists api.get_public_municipal_contracts(integer);

create function api.get_public_municipal_contracts(
  page_size integer default 100,
  page_offset integer default 0
)
returns table (
  contract_id uuid,
  source_contract_id text,
  contract_number text,
  contract_object text,
  supplier_name text,
  supplier_document_kind text,
  supplier_document text,
  contract_value_text text,
  referential_value_text text,
  modality_code text,
  category_code text,
  validity_start_text text,
  validity_end_text text,
  document_url text,
  api_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  document_preserved boolean,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with candidates as (
    select
      record.id,
      record.payload,
      record.created_at,
      artifact.source_url as api_source_url,
      artifact.sha256 as artifact_sha256,
      artifact.retrieved_at,
      document.sha256 as document_artifact_sha256,
      document.id is not null as document_preserved,
      regexp_replace(
        coalesce(record.payload ->> 'documento', ''), '[^0-9]', '', 'g'
      ) as document_digits,
      row_number() over (
        partition by coalesce(record.source_record_key, record.id::text)
        order by record.created_at desc, record.id desc
      ) as current_row
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    left join lateral (
      select child.id, child.sha256
      from raw.raw_artifacts as child
      where child.parent_artifact_id = artifact.id
        and child.artifact_kind = 'document'
        and child.metadata ->> 'schema_name'
          = 'municipal-transparency-document'
        and child.metadata ->> 'source_record_key'
          = record.source_record_key
      order by child.created_at desc, child.id desc
      limit 1
    ) as document on true
    where record.record_type = 'municipal_transparency_contratos'
      and nullif(btrim(record.payload ->> 'contratoNumero'), '') is not null
      and nullif(btrim(record.payload ->> 'favorecido'), '') is not null
      and record.payload ->> 'url' ~ '^https://'
  )
  select
    candidate.id,
    nullif(btrim(candidate.payload ->> 'id'), ''),
    btrim(candidate.payload ->> 'contratoNumero'),
    nullif(btrim(candidate.payload ->> 'contratoObjeto'), ''),
    btrim(candidate.payload ->> 'favorecido'),
    case
      when length(candidate.document_digits) = 14 then 'cnpj'
      when length(candidate.document_digits) = 11 then 'cpf_pessoa_fisica'
      when candidate.document_digits = '' then 'nao_informado'
      else 'outro_formato'
    end,
    case
      when length(candidate.document_digits) = 14
      then candidate.document_digits
    end,
    nullif(btrim(candidate.payload ->> 'valor_contrato'), ''),
    nullif(btrim(candidate.payload ->> 'valor_referencial'), ''),
    nullif(btrim(candidate.payload ->> 'modalidade'), ''),
    nullif(btrim(candidate.payload ->> 'categoria'), ''),
    nullif(btrim(candidate.payload ->> 'vigencia_inicio'), ''),
    nullif(btrim(candidate.payload ->> 'vigencia'), ''),
    candidate.payload ->> 'url',
    candidate.api_source_url,
    candidate.artifact_sha256,
    candidate.document_artifact_sha256,
    candidate.document_preserved,
    candidate.retrieved_at,
    'municipal-contracts/1.0.0'::text
  from candidates as candidate
  where candidate.current_row = 1
  order by
    case
      when candidate.payload ->> 'id' ~ '^[0-9]+$'
      then (candidate.payload ->> 'id')::integer
    end desc nulls last,
    candidate.created_at desc,
    candidate.id desc
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.get_public_municipal_contracts(integer, integer) from public;
grant execute on function api.get_public_municipal_contracts(integer, integer)
  to anon, authenticated;

comment on function api.get_public_municipal_contracts(integer, integer) is
  'Contratos do portal municipal como espelho literal: valores em texto da fonte, CNPJ publicado, CPF de pessoa fisica nunca exposto.';

drop function if exists api.get_public_municipal_procurement_processes(integer);

create function api.get_public_municipal_procurement_processes(
  page_size integer default 100,
  page_offset integer default 0
)
returns table (
  process_record_id uuid,
  source_process_id text,
  process_number text,
  notice_number text,
  publication_date_text text,
  opening_date_text text,
  process_object text,
  bidding_type_code text,
  modality_code text,
  category_code text,
  situation_code text,
  result_code text,
  estimated_value_text text,
  awarded_value_text text,
  api_source_url text,
  artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with candidates as (
    select
      record.id,
      record.payload,
      record.created_at,
      artifact.source_url as api_source_url,
      artifact.sha256 as artifact_sha256,
      artifact.retrieved_at,
      row_number() over (
        partition by coalesce(
          nullif(btrim(record.payload ->> 'id'), ''),
          record.source_record_key
        )
        order by record.created_at desc, record.id desc
      ) as current_row
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    where record.record_type = 'municipal_transparency_processos'
      and nullif(btrim(record.payload ->> 'numero_processo'), '') is not null
      and nullif(btrim(record.payload ->> 'objeto'), '') is not null
  )
  select
    candidate.id,
    nullif(btrim(candidate.payload ->> 'id'), ''),
    btrim(candidate.payload ->> 'numero_processo'),
    nullif(btrim(candidate.payload ->> 'numero_edital'), ''),
    nullif(btrim(candidate.payload ->> 'data_publicacao'), ''),
    nullif(btrim(candidate.payload ->> 'data_abertura'), ''),
    btrim(candidate.payload ->> 'objeto'),
    nullif(btrim(candidate.payload ->> 'tipo_licitacao'), ''),
    nullif(btrim(candidate.payload ->> 'modalidade_licitacao'), ''),
    nullif(btrim(candidate.payload ->> 'categoria_licitacao'), ''),
    nullif(btrim(candidate.payload ->> 'situacao'), ''),
    nullif(btrim(candidate.payload ->> 'resultado'), ''),
    nullif(btrim(candidate.payload ->> 'valor_estimado'), ''),
    nullif(btrim(candidate.payload ->> 'valor'), ''),
    candidate.api_source_url,
    candidate.artifact_sha256,
    candidate.retrieved_at,
    'municipal-procurement-processes/1.0.0'::text
  from candidates as candidate
  where candidate.current_row = 1
  order by
    case
      when candidate.payload ->> 'data_publicacao'
        ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (candidate.payload ->> 'data_publicacao')::date
    end desc nulls last,
    case
      when candidate.payload ->> 'id' ~ '^[0-9]+$'
      then (candidate.payload ->> 'id')::integer
    end desc nulls last,
    candidate.created_at desc,
    candidate.id desc
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.get_public_municipal_procurement_processes(integer, integer) from public;
grant execute on function api.get_public_municipal_procurement_processes(integer, integer)
  to anon, authenticated;

comment on function api.get_public_municipal_procurement_processes(integer, integer) is
  'Processos licitatorios do portal municipal como espelho literal: valores e codigos em texto da fonte; estado mais recente por processo.';

notify pgrst, 'reload schema';

commit;
