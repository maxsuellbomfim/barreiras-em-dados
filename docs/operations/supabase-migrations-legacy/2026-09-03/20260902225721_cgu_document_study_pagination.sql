begin;

-- A lista documental da CGU deve atravessar a API em páginas pequenas. As
-- contagens e opções de filtro continuam calculadas sobre o acervo completo.
-- O ranking financeiro permanece em sua RPC própria e não é recalculado aqui.

create function api.get_public_cgu_federal_amendment_document_study(
  page_size integer default 25,
  page_offset integer default 0,
  archive_year_filter smallint default null,
  author_key_filter text default null,
  expense_stage_filter text default null,
  query_filter text default null
)
returns table (
  items jsonb,
  total_count bigint,
  catalog_count bigint,
  available_years smallint[],
  available_authors jsonb,
  available_stages text[],
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  normalized_author_key text := nullif(btrim(author_key_filter), '');
  normalized_stage text := nullif(btrim(expense_stage_filter), '');
  normalized_query text := nullif(
    translate(
      lower(btrim(query_filter)),
      'áàâãäéèêëíìîïóòôõöúùûüç',
      'aaaaaeeeeiiiiooooouuuuc'
    ),
    ''
  );
begin
  if page_size is null or page_size < 1 or page_size > 50 then
    raise exception 'page_size deve estar entre 1 e 50'
      using errcode = '22023';
  end if;
  if page_offset is null or page_offset < 0 or page_offset > 5000 then
    raise exception 'page_offset deve estar entre 0 e 5000'
      using errcode = '22023';
  end if;
  if archive_year_filter is not null
    and (archive_year_filter < 2021 or archive_year_filter > 2100)
  then
    raise exception 'archive_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null
    and length(normalized_author_key) > 200
  then
    raise exception 'author_key_filter excede 200 caracteres'
      using errcode = '22023';
  end if;
  if normalized_stage is not null
    and normalized_stage not in ('commitment', 'liquidation', 'payment')
  then
    raise exception 'expense_stage_filter invalido'
      using errcode = '22023';
  end if;
  if query_filter is not null and length(query_filter) > 100 then
    raise exception 'query_filter excede 100 caracteres'
      using errcode = '22023';
  end if;

  return query
  with catalog as materialized (
    select document.*
    from territory.cgu_federal_amendment_documents as document
  ),
  filtered as materialized (
    select document.*
    from catalog as document
    where (
        archive_year_filter is null
        or document.archive_year = archive_year_filter
      )
      and (
        normalized_author_key is null
        or document.author_key = normalized_author_key
      )
      and (
        normalized_stage is null
        or document.expense_stage = normalized_stage
      )
      and (
        normalized_query is null
        or position(
          normalized_query in translate(
            lower(concat_ws(
              ' ',
              document.amendment_code,
              document.amendment_number,
              document.author_name,
              document.document_code,
              document.beneficiary_name,
              document.beneficiary_municipality,
              document.locality,
              document.agency_name,
              document.superior_agency_name,
              document.function_name,
              document.subfunction_name,
              document.program_name,
              document.action_name,
              document.citizen_language
            )),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
          )
        ) > 0
      )
  ),
  page_rows as (
    select filtered.*
    from filtered
    order by
      filtered.document_date desc,
      filtered.document_code,
      filtered.source_row_number
    limit page_size
    offset page_offset
  ),
  authors as (
    select distinct on (catalog.author_key)
      catalog.author_key,
      catalog.author_name
    from catalog
    order by catalog.author_key, catalog.document_date desc,
      catalog.raw_record_id desc
  )
  select
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'archive_year', page_rows.archive_year,
          'amendment_year', page_rows.amendment_year,
          'amendment_code', page_rows.amendment_code,
          'amendment_number', page_rows.amendment_number,
          'amendment_type', page_rows.amendment_type,
          'author_kind', page_rows.author_kind,
          'author_key', page_rows.author_key,
          'author_name', page_rows.author_name,
          'document_date', page_rows.document_date,
          'document_code', page_rows.document_code,
          'expense_stage', page_rows.expense_stage,
          'expense_stage_source', page_rows.expense_stage_source,
          'committed_amount', page_rows.committed_amount,
          'paid_amount', page_rows.paid_amount,
          'beneficiary_name', page_rows.beneficiary_name,
          'beneficiary_type', page_rows.beneficiary_type,
          'beneficiary_municipality', page_rows.beneficiary_municipality,
          'locality', page_rows.locality,
          'agency_name', page_rows.agency_name,
          'superior_agency_name', page_rows.superior_agency_name,
          'function_name', page_rows.function_name,
          'subfunction_name', page_rows.subfunction_name,
          'program_name', page_rows.program_name,
          'action_name', page_rows.action_name,
          'citizen_language', page_rows.citizen_language,
          'source_row_number', page_rows.source_row_number,
          'source_url', page_rows.source_url,
          'artifact_sha256', page_rows.artifact_sha256,
          'collected_at', page_rows.collected_at,
          'methodology_version',
            'cgu-federal-amendment-documents/1.0.0'
        )
        order by page_rows.document_date desc, page_rows.document_code,
          page_rows.source_row_number
      )
      from page_rows
    ), '[]'::jsonb) as items,
    (select count(*) from filtered) as total_count,
    (select count(*) from catalog) as catalog_count,
    coalesce((
      select array_agg(years.archive_year order by years.archive_year desc)
      from (
        select distinct catalog.archive_year
        from catalog
      ) as years
    ), '{}'::smallint[]) as available_years,
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'author_key', authors.author_key,
          'author_name', authors.author_name
        )
        order by authors.author_name, authors.author_key
      )
      from authors
    ), '[]'::jsonb) as available_authors,
    coalesce((
      select array_agg(
        stages.expense_stage
        order by case stages.expense_stage
          when 'commitment' then 1
          when 'liquidation' then 2
          when 'payment' then 3
          else 4
        end
      )
      from (
        select distinct catalog.expense_stage
        from catalog
      ) as stages
    ), '{}'::text[]) as available_stages,
    'cgu-federal-amendment-document-study/1.0.0'::text
      as methodology_version;
end;
$function$;

revoke all on function api.get_public_cgu_federal_amendment_document_study(
  integer, integer, smallint, text, text, text
) from public;
grant execute on function api.get_public_cgu_federal_amendment_document_study(
  integer, integer, smallint, text, text, text
) to anon, authenticated;

comment on function api.get_public_cgu_federal_amendment_document_study(
  integer, integer, smallint, text, text, text
) is
  'Documentos federais da CGU paginados no servidor; contagens e filtros cobrem o acervo inteiro sem recalcular ranking ou somar fontes.';

notify pgrst, 'reload schema';

commit;
