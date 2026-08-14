begin;

create function api.get_public_bahia_state_loa_execution(
  fiscal_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 100
)
returns table (
  fiscal_year smallint,
  amendment_number text,
  author_external_code text,
  author_key text,
  author_name text,
  authorized_amount numeric(20,2),
  official_description text,
  page_number integer,
  loa_evidence_text text,
  loa_source_url text,
  loa_source_artifact_sha256 text,
  loa_evidence_sha256 text,
  execution_status text,
  loa_scope_occurrences integer,
  execution_occurrences integer,
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  execution_source_url text,
  execution_source_artifact_sha256 text,
  execution_evidence_sha256 text,
  execution_source_collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
  normalized_author_key text := nullif(btrim(author_key_filter), '');
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2022 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null and length(normalized_author_key) > 200 then
    raise exception 'autor da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  select
    reconciliation.fiscal_year,
    reconciliation.amendment_number,
    reconciliation.author_external_code,
    reconciliation.author_key,
    reconciliation.author_name,
    reconciliation.authorized_amount,
    reconciliation.official_description,
    reconciliation.page_number,
    reconciliation.loa_evidence_text,
    reconciliation.loa_source_url,
    reconciliation.loa_source_artifact_sha256,
    reconciliation.loa_evidence_sha256,
    case reconciliation.reconciliation_status
      when 'matched_bidirectional_unique' then 'execution_confirmed'
      when 'blocked_non_unique_loa_key' then 'ambiguous_official_key'
      when 'blocked_non_unique_execution_key' then 'ambiguous_official_key'
      when 'not_found_in_execution_source'
        then 'not_found_in_execution_source'
      else 'scope_not_available'
    end as execution_status,
    reconciliation.loa_scope_occurrences,
    reconciliation.execution_occurrences,
    reconciliation.committed_amount,
    reconciliation.liquidated_amount,
    reconciliation.paid_amount,
    reconciliation.execution_source_url,
    reconciliation.execution_source_artifact_sha256,
    reconciliation.execution_evidence_sha256,
    reconciliation.execution_source_collected_at,
    'bahia-state-loa-public-execution/1.0.0'::text
  from territory.bahia_state_loa_execution_reconciliation as reconciliation
  where (
    fiscal_year_filter is null
    or reconciliation.fiscal_year = fiscal_year_filter
  )
    and (
      normalized_author_key is null
      or reconciliation.author_key = normalized_author_key
    )
  order by
    reconciliation.fiscal_year desc,
    reconciliation.authorized_amount desc,
    reconciliation.author_name,
    reconciliation.amendment_number,
    reconciliation.page_number
  limit page_size;
end;
$$;

create function api.get_public_bahia_state_loa_execution_summary(
  fiscal_year_filter smallint
)
returns table (
  fiscal_year smallint,
  total_amendment_count integer,
  matched_amendment_count integer,
  ambiguous_amendment_count integer,
  not_found_amendment_count integer,
  unavailable_scope_count integer,
  authorized_total numeric(20,2),
  matched_authorized_total numeric(20,2),
  committed_total numeric(20,2),
  liquidated_total numeric(20,2),
  paid_total numeric(20,2),
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
begin
  if fiscal_year_filter is null
    or fiscal_year_filter < 2022
    or fiscal_year_filter > current_fiscal_year
  then
    raise exception 'ano do resumo da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  select
    fiscal_year_filter,
    count(*)::integer,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_non_unique_loa_key',
        'blocked_non_unique_execution_key'
      )
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'not_found_in_execution_source'
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_scope_year_not_indexed',
        'blocked_scope_not_collected'
      )
    )::integer,
    sum(reconciliation.authorized_amount)::numeric(20,2),
    sum(reconciliation.authorized_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.committed_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.liquidated_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.paid_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    'bahia-state-loa-public-execution-summary/1.0.0'::text
  from territory.bahia_state_loa_execution_reconciliation as reconciliation
  where reconciliation.fiscal_year = fiscal_year_filter
  having count(*) > 0;
end;
$$;

revoke all on function api.get_public_bahia_state_loa_execution(
  smallint, text, integer
) from public;
revoke all on function api.get_public_bahia_state_loa_execution_summary(
  smallint
) from public;

grant execute on function api.get_public_bahia_state_loa_execution(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_bahia_state_loa_execution_summary(
  smallint
) to anon, authenticated;

comment on function api.get_public_bahia_state_loa_execution(
  smallint, text, integer
) is
  'Execucao estadual ligada a autorizacoes de Barreiras somente por chave bidirecionalmente unica; bloqueios conservam valores nulos.';
comment on function api.get_public_bahia_state_loa_execution_summary(
  smallint
) is
  'Cobertura e totais exatos da execucao estadual; valores executados somam somente correspondencias unicas.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:publish-bahia-state-loa-execution',
  'reconciliation.public_projection_created',
  'api.get_public_bahia_state_loa_execution',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'bahia-state-loa-public-execution/1.0.0',
    'financial_values_require_status', 'matched_bidirectional_unique'
  ),
  jsonb_build_object(
    'blocked_values_are_null', true,
    'public_private_view_access', false
  )
);

notify pgrst, 'reload schema';

commit;
