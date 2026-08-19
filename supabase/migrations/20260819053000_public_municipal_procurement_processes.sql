begin;

-- Publica os processos licitatorios do portal municipal como espelho literal.
-- Regras inegociaveis aplicadas aqui:
--   * valores permanecem TEXTO literal da fonte ("14237586.12"); nenhuma
--     conversao ou soma sem regra deterministica versionada;
--   * situacao e resultado sao publicados como codigos literais: a API da
--     fonte nao publica legenda para eles; modalidade e categoria tambem
--     saem como codigos (a legenda oficial exibida no site vem do proprio
--     filtro do portal e vive versionada na camada web);
--   * um processo e MUTAVEL na fonte (situacao avanca); a chave bruta e
--     enderecada por conteudo, entao a projecao deduplica pelo id estavel
--     do processo e entrega apenas o estado mais recente preservado.

create function api.get_public_municipal_procurement_processes(
  page_size integer default 100
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
  limit page_size;
end;
$function$;

revoke all on function api.get_public_municipal_procurement_processes(integer)
  from public;
grant execute on function api.get_public_municipal_procurement_processes(integer)
  to anon, authenticated;

comment on function
  api.get_public_municipal_procurement_processes(integer) is
  'Processos licitatorios do portal municipal como espelho literal: valores e codigos em texto da fonte; estado mais recente por processo.';

notify pgrst, 'reload schema';

commit;
