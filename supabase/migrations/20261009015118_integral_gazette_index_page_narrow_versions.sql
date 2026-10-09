begin;

-- O CTE public_versions (version.*) era referenciado duas vezes e por isso
-- materializado com o texto integral de todos os documentos; depois do
-- backfill 2021-2022 a função ordenava em disco (1,3 s fora de pico, acima
-- de 3 s na janela da sonda pública). O filtro de publicação vai direto nas
-- duas junções. Mesmo resultado (assinatura idêntica das páginas 1 e 20 em
-- 09/10/2026); 1,3 s -> 0,07 s.
create or replace function api.get_integral_gazette_index_page(
  page_size integer default 21,
  page_offset integer default 0
)
returns table (
  edition integer,
  edition_year integer,
  edition_date date,
  artifact_sha256 text,
  documents jsonb,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 101 then
    raise exception 'page_size deve estar entre 1 e 101' using errcode = '22023';
  end if;
  if page_offset < 0 then
    raise exception 'page_offset deve ser maior ou igual a zero' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key
    from editorial.gazette_document_versions as version
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
      version.created_at desc, version.id desc
  ), page_editions as materialized (
    select edition_record.*
    from all_batches as edition_record
    where exists (
      select 1 from editorial.gazette_document_versions as version
      where version.edition = edition_record.edition
        and version.edition_year = edition_record.edition_year
        and version.batch_idempotency_key = edition_record.batch_idempotency_key
        and version.publication_status in ('validated', 'edition_fallback')
        and version.published_at is not null
    )
    order by edition_record.edition_year desc, edition_record.edition desc
    limit page_size offset page_offset
  )
  -- Sem CTE com version.*: ele era materializado com o texto integral de
  -- todos os documentos (ordenação em disco depois do backfill 2021-2022).
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', editorial.mask_cpf_v1(version.literal_title),
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order),
    'integral-gazette-documents/1.1.0'::text
  from page_editions as edition_record
  join editorial.gazette_document_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
   and version.publication_status in ('validated', 'edition_fallback')
   and version.published_at is not null
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc;
end;
$function$;

commit;
