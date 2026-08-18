begin;

-- Publica os contratos do portal municipal como espelho literal da fonte.
-- Regras inegociaveis aplicadas aqui:
--   * valores monetarios permanecem TEXTO literal da fonte ("R$ 105.460,50");
--     nenhuma conversao ou soma acontece sem regra deterministica versionada;
--   * o campo `documento` da fonte mistura CNPJ e CPF; CPF de pessoa fisica
--     NUNCA e publicado — apenas a classificacao. So CNPJ (14 digitos) sai.
--   * codigos de modalidade/categoria sao publicados como codigos, porque a
--     fonte nao publica legenda.

create function api.get_public_municipal_contracts(
  page_size integer default 100
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
  limit page_size;
end;
$function$;

revoke all on function api.get_public_municipal_contracts(integer) from public;
grant execute on function api.get_public_municipal_contracts(integer)
  to anon, authenticated;

comment on function api.get_public_municipal_contracts(integer) is
  'Contratos do portal municipal como espelho literal: valores em texto da fonte, CNPJ publicado, CPF de pessoa fisica nunca exposto.';

notify pgrst, 'reload schema';

commit;
