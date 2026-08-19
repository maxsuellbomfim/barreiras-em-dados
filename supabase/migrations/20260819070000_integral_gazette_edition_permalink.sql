begin;

-- URL propria por edicao do Diario: devolve uma unica edicao integral com
-- seus documentos, no mesmo contrato literal da pagina paginada. Mantem a
-- regra de um lote por edicao (o mais novo, preferindo a coleta direta).

create function api.get_integral_gazette_edition(
  target_edition_year integer,
  target_edition integer
)
returns table (
  edition integer,
  edition_year integer,
  edition_date date,
  artifact_sha256 text,
  documents jsonb,
  methodology_version text
)
language plpgsql stable security definer set search_path = ''
as $function$
begin
  if target_edition_year < 2000 or target_edition_year > 2100 then
    raise exception 'ano da edição fora do intervalo' using errcode = '22023';
  end if;
  if target_edition < 1 then
    raise exception 'edição deve ser positiva' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key
    from editorial.gazette_document_versions as version
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    where version.edition_year = target_edition_year
      and version.edition = target_edition
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
      version.created_at desc, version.id desc
  ), public_versions as (
    select version.*
    from editorial.gazette_document_versions as version
    where version.publication_status in ('validated', 'edition_fallback')
      and version.published_at is not null
      and version.edition_year = target_edition_year
      and version.edition = target_edition
  )
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', version.literal_title,
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'full_text', version.full_text,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order),
    'integral-gazette-documents/1.0.0'::text
  from all_batches as edition_record
  join public_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year, artifact.sha256;
end;
$function$;

revoke all on function api.get_integral_gazette_edition(integer, integer)
  from public;
grant execute on function api.get_integral_gazette_edition(integer, integer)
  to anon, authenticated;
comment on function api.get_integral_gazette_edition(integer, integer) is
  'Uma edicao integral do Diario Oficial com seus documentos literais, para URL propria compartilhavel.';

notify pgrst, 'reload schema';

commit;
