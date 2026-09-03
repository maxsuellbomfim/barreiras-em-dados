begin;

-- A leitura detalhada estadual usa uma única página para autorização e para a
-- execução correspondente. Ranking e totais continuam em RPCs próprias, sobre
-- o universo completo, para não confundir paginação com cobertura financeira.

create function api.get_public_bahia_state_loa_study(
  fiscal_year_filter smallint,
  page_size integer default 12,
  page_offset integer default 0
)
returns table (
  amendment_items jsonb,
  execution_items jsonb,
  total_count bigint,
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

  return query
  with filtered as materialized (
    select amendment.*
    from territory.bahia_state_loa_amendments as amendment
    where amendment.fiscal_year = fiscal_year_filter
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
  page_execution as materialized (
    select
      amendment.evidence_sha256 as page_evidence_sha256,
      reconciliation.*
    from page_rows as amendment
    join territory.bahia_state_loa_execution_reconciliation_snapshot
      as reconciliation
      on reconciliation.fiscal_year = amendment.fiscal_year
      and reconciliation.loa_evidence_sha256 = amendment.evidence_sha256
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
          'loa_evidence_text', execution.loa_evidence_text,
          'loa_source_url', execution.loa_source_url,
          'loa_source_artifact_sha256',
            execution.loa_source_artifact_sha256,
          'loa_evidence_sha256', execution.loa_evidence_sha256,
          'execution_status', case execution.reconciliation_status
            when 'matched_bidirectional_unique' then 'execution_confirmed'
            when 'blocked_non_unique_loa_key' then 'ambiguous_official_key'
            when 'blocked_non_unique_execution_key' then 'ambiguous_official_key'
            when 'not_found_in_execution_source'
              then 'not_found_in_execution_source'
            when 'blocked_scope_year_not_indexed'
              then 'official_link_key_unavailable'
            else 'scope_not_available'
          end,
          'loa_scope_occurrences', execution.loa_scope_occurrences,
          'execution_occurrences', execution.execution_occurrences,
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
          execution.loa_evidence_sha256
      )
      from page_execution as execution
    ), '[]'::jsonb) as execution_items,
    (select count(*) from filtered) as total_count,
    'bahia-state-loa-study/1.0.0'::text as methodology_version;
end;
$function$;

revoke all on function api.get_public_bahia_state_loa_study(
  smallint, integer, integer
) from public;
grant execute on function api.get_public_bahia_state_loa_study(
  smallint, integer, integer
) to anon, authenticated;

comment on function api.get_public_bahia_state_loa_study(
  smallint, integer, integer
) is
  'Pagina autorizacoes estaduais de Barreiras e somente suas ligacoes de execucao; ranking e totais permanecem integrais e separados.';

notify pgrst, 'reload schema';

commit;
