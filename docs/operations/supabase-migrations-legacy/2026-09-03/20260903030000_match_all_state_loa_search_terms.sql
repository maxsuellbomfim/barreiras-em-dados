begin;

-- A busca inicial exigia que todas as palavras fossem contíguas. Esta versão
-- mantém o contrato e passa a exigir cada termo normalizado em qualquer ponto
-- do nome, número ou objeto, como uma pessoa espera de uma busca textual.

create or replace function api.get_public_bahia_state_loa_study_filtered(
  fiscal_year_filter smallint,
  page_size integer default 12,
  page_offset integer default 0,
  author_key_filter text default null,
  execution_status_filter text default null,
  query_filter text default null
)
returns table (
  amendment_items jsonb,
  execution_items jsonb,
  total_count bigint,
  catalog_count bigint,
  available_authors jsonb,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
  normalized_author_key text := nullif(btrim(author_key_filter), '');
  normalized_execution_status text := nullif(
    btrim(execution_status_filter), ''
  );
  normalized_query text := nullif(
    translate(
      lower(btrim(query_filter)),
      'áàâãäéèêëíìîïóòôõöúùûüç',
      'aaaaaeeeeiiiiooooouuuuc'
    ),
    ''
  );
begin
  if fiscal_year_filter is null
    or fiscal_year_filter < 2022
    or fiscal_year_filter > current_fiscal_year
  then
    raise exception 'ano do estudo estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 25 then
    raise exception 'page_size do estudo estadual deve estar entre 1 e 25'
      using errcode = '22023';
  end if;
  if page_offset is null or page_offset < 0 or page_offset > 5000 then
    raise exception 'page_offset do estudo estadual deve estar entre 0 e 5000'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null
    and length(normalized_author_key) > 200
  then
    raise exception 'author_key_filter excede 200 caracteres'
      using errcode = '22023';
  end if;
  if normalized_execution_status is not null
    and normalized_execution_status not in (
      'execution_confirmed',
      'ambiguous_official_key',
      'not_found_in_execution_source',
      'official_link_key_unavailable',
      'scope_not_available'
    )
  then
    raise exception 'execution_status_filter invalido'
      using errcode = '22023';
  end if;
  if query_filter is not null and length(query_filter) > 100 then
    raise exception 'query_filter excede 100 caracteres'
      using errcode = '22023';
  end if;

  return query
  with catalog as materialized (
    select
      amendment.*,
      reconciliation.reconciliation_status,
      reconciliation.loa_scope_occurrences,
      reconciliation.execution_occurrences,
      reconciliation.committed_amount,
      reconciliation.liquidated_amount,
      reconciliation.paid_amount,
      reconciliation.execution_source_url,
      reconciliation.execution_source_artifact_sha256,
      reconciliation.execution_evidence_sha256,
      reconciliation.execution_source_collected_at,
      case reconciliation.reconciliation_status
        when 'matched_bidirectional_unique' then 'execution_confirmed'
        when 'blocked_non_unique_loa_key' then 'ambiguous_official_key'
        when 'blocked_non_unique_execution_key' then 'ambiguous_official_key'
        when 'not_found_in_execution_source'
          then 'not_found_in_execution_source'
        when 'blocked_scope_year_not_indexed'
          then 'official_link_key_unavailable'
        else 'scope_not_available'
      end as public_execution_status
    from territory.bahia_state_loa_amendments as amendment
    left join territory.bahia_state_loa_execution_reconciliation_snapshot
      as reconciliation
      on reconciliation.fiscal_year = amendment.fiscal_year
      and reconciliation.loa_evidence_sha256 = amendment.evidence_sha256
    where amendment.fiscal_year = fiscal_year_filter
  ),
  filtered as materialized (
    select amendment.*
    from catalog as amendment
    where (
        normalized_author_key is null
        or amendment.author_key = normalized_author_key
      )
      and (
        normalized_execution_status is null
        or amendment.public_execution_status = normalized_execution_status
      )
      and (
        normalized_query is null
        or not exists (
          select 1
          from regexp_split_to_table(
            normalized_query,
            '[[:space:]]+'
          ) as search_term(value)
          where search_term.value <> ''
            and position(
              search_term.value in translate(
                lower(concat_ws(
                  ' ',
                  amendment.author_name,
                  amendment.amendment_number,
                  amendment.official_description
                )),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
              )
            ) = 0
        )
      )
  ),
  page_rows as materialized (
    select amendment.*
    from filtered as amendment
    order by
      amendment.authorized_amount desc,
      amendment.author_name,
      amendment.amendment_number,
      amendment.page_number,
      amendment.evidence_sha256
    limit page_size
    offset page_offset
  ),
  authors as (
    select distinct on (catalog.author_key)
      catalog.author_key,
      catalog.author_name
    from catalog
    order by catalog.author_key, catalog.author_name
  )
  select
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'fiscal_year', amendment.fiscal_year,
          'amendment_number', amendment.amendment_number,
          'author_external_code', amendment.author_external_code,
          'author_key', amendment.author_key,
          'author_name', amendment.author_name,
          'authorized_amount', amendment.authorized_amount,
          'official_description', amendment.official_description,
          'annex_code', amendment.annex_code,
          'budget_unit_code', amendment.budget_unit_code,
          'agency_code', amendment.agency_code,
          'action_code', amendment.action_code,
          'page_number', amendment.page_number,
          'evidence_text', amendment.evidence_text,
          'financial_stage', 'authorized',
          'source_url', amendment.source_url,
          'source_artifact_sha256', amendment.source_artifact_sha256,
          'evidence_sha256', amendment.evidence_sha256,
          'methodology_version', 'bahia-state-loa-amendments/1.0.0'
        )
        order by
          amendment.authorized_amount desc,
          amendment.author_name,
          amendment.amendment_number,
          amendment.page_number,
          amendment.evidence_sha256
      )
      from page_rows as amendment
    ), '[]'::jsonb) as amendment_items,
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'fiscal_year', execution.fiscal_year,
          'amendment_number', execution.amendment_number,
          'author_external_code', execution.author_external_code,
          'author_key', execution.author_key,
          'author_name', execution.author_name,
          'authorized_amount', execution.authorized_amount,
          'official_description', execution.official_description,
          'page_number', execution.page_number,
          'loa_evidence_text', execution.evidence_text,
          'loa_source_url', execution.source_url,
          'loa_source_artifact_sha256', execution.source_artifact_sha256,
          'loa_evidence_sha256', execution.evidence_sha256,
          'execution_status', execution.public_execution_status,
          'loa_scope_occurrences',
            coalesce(execution.loa_scope_occurrences, 0),
          'execution_occurrences',
            coalesce(execution.execution_occurrences, 0),
          'committed_amount', execution.committed_amount,
          'liquidated_amount', execution.liquidated_amount,
          'paid_amount', execution.paid_amount,
          'execution_source_url', execution.execution_source_url,
          'execution_source_artifact_sha256',
            execution.execution_source_artifact_sha256,
          'execution_evidence_sha256', execution.execution_evidence_sha256,
          'execution_source_collected_at',
            execution.execution_source_collected_at,
          'methodology_version',
            'bahia-state-loa-public-execution/1.1.0'
        )
        order by
          execution.authorized_amount desc,
          execution.author_name,
          execution.amendment_number,
          execution.page_number,
          execution.evidence_sha256
      )
      from page_rows as execution
    ), '[]'::jsonb) as execution_items,
    (select count(*) from filtered) as total_count,
    (select count(*) from catalog) as catalog_count,
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
    'bahia-state-loa-study/1.1.0'::text as methodology_version;
end;
$function$;

comment on function api.get_public_bahia_state_loa_study_filtered(
  smallint, integer, integer, text, text, text
) is
  'Pesquisa por todos os termos e pagina autorizacoes estaduais de Barreiras; totais filtrados e acervo anual permanecem distintos.';

notify pgrst, 'reload schema';

commit;
