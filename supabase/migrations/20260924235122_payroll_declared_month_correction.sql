begin;

-- Folha de julho/2026: o portal listou o PDF de agosto/2026
-- (SERVIDORES080926163024.pdf, cabeçalho "MÊS/ANO: Agosto / 2026") também
-- como julho, e a versão 4 de julho substituiu a versão 3 correta
-- (SERVIDORES060826145033.pdf, "Julho / 2026"). A correção é append-only:
-- a versão 4 é invalidada com o PDF como evidência e a regra de versão
-- vigente passa a ignorar sucessor invalidado, devolvendo a versão 3.

alter table hr.payroll_report_aggregate_invalidations
  drop constraint payroll_report_invalidations_reason_allowed;
alter table hr.payroll_report_aggregate_invalidations
  add constraint payroll_report_invalidations_reason_allowed
  check (reason_code in (
    'mixed_payroll_cycle_header',
    'non_staff_catalog_title',
    'missing_staff_catalog_title',
    'mismatched_source_endpoint',
    'declared_month_mismatch'
  ));

insert into hr.payroll_report_aggregate_invalidations (
  aggregate_id,
  evidence_artifact_id,
  reason_code,
  invalidator_version,
  details,
  invalidated_at
)
select
  aggregate.id,
  artifact.id,
  'declared_month_mismatch',
  'payroll-declared-month-invalidation/1.0.0',
  jsonb_build_object(
    'catalog_reference_month', '2026-07-01',
    'declared_reference_month', '2026-08-01',
    'declared_header', 'MÊS/ANO.....: Agosto / 2026',
    'parser_version', aggregate.parser_version,
    'artifact_sha256', artifact.sha256
  ),
  statement_timestamp()
from hr.payroll_report_aggregates as aggregate
join raw.raw_artifacts as artifact
  on artifact.id = aggregate.source_document_artifact_id
where aggregate.reference_month = date '2026-07-01'
  and aggregate.report_kind = 'municipal_staff'
  and aggregate.payroll_cycle = 'regular'
  and artifact.sha256 =
    'fd2853ff283afa821d2e50b6b361ba35d30c09cf350f38bc0d28a2e891f61c16'
on conflict (aggregate_id) do nothing;

create or replace function api.get_public_payroll_months(
  page_size integer default 24
)
returns table (
  reference_month text,
  public_body_name text,
  employee_count integer,
  gross_amount numeric(20,2),
  deduction_amount numeric(20,2),
  net_amount numeric(20,2),
  subtotal_count integer,
  document_count integer,
  source_url text,
  artifact_sha256 text,
  source_retrieved_at timestamptz,
  parser_version text,
  source_documents jsonb
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 60 then
    raise exception 'limite de meses da folha invalido'
      using errcode = '22023';
  end if;

  return query
  with current_components as (
    select
      aggregate.*,
      body.name as body_name,
      artifact.source_url as document_url,
      artifact.sha256 as document_sha256,
      artifact.retrieved_at as document_retrieved_at
    from hr.payroll_report_aggregates as aggregate
    join org.public_bodies as body on body.id = aggregate.public_body_id
    join raw.raw_artifacts as artifact
      on artifact.id = aggregate.source_document_artifact_id
    where aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
          -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
          -- não substitui a versão anterior.
          and not exists (
            select 1
            from hr.payroll_report_aggregate_invalidations as successor_invalidation
            where successor_invalidation.aggregate_id = successor.id
          )
      )
  ), monthly_totals as (
    select
      component.reference_month,
      component.public_body_id,
      max(component.body_name) as body_name,
      max(component.employee_count) filter (
        where component.payroll_cycle = 'regular'
      )::integer as regular_employee_count,
      sum(component.gross_amount)::numeric(20,2) as total_gross,
      sum(component.deduction_amount)::numeric(20,2) as total_deduction,
      sum(component.net_amount)::numeric(20,2) as total_net,
      sum(component.subtotal_count)::integer as total_subtotals,
      count(*)::integer as total_documents,
      (array_agg(
        component.document_url order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_url,
      (array_agg(
        component.document_sha256 order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_sha256,
      (array_agg(
        component.document_retrieved_at order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_retrieved_at,
      jsonb_agg(
        jsonb_build_object(
          'payroll_cycle', component.payroll_cycle,
          'source_url', component.document_url,
          'artifact_sha256', component.document_sha256,
          'source_retrieved_at', component.document_retrieved_at,
          'parser_version', component.parser_version
        ) order by case component.payroll_cycle
          when 'regular' then 1
          when 'thirteenth_advance' then 2
          when 'thirteenth_final' then 3
        end
      ) as documents
    from current_components as component
    group by component.reference_month, component.public_body_id
    having count(*) filter (
      where component.payroll_cycle = 'regular'
    ) = 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_advance'
      ) <= 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_final'
      ) <= 1
  )
  select
    to_char(monthly.reference_month, 'YYYY-MM-DD'),
    monthly.body_name,
    monthly.regular_employee_count,
    monthly.total_gross,
    monthly.total_deduction,
    monthly.total_net,
    monthly.total_subtotals,
    monthly.total_documents,
    monthly.regular_document_url,
    monthly.regular_document_sha256,
    monthly.regular_document_retrieved_at,
    'payroll-monthly-total/1.0.0'::text,
    monthly.documents
  from monthly_totals as monthly
  order by monthly.reference_month desc, monthly.public_body_id
  limit page_size;
end;
$function$;

create or replace function api.get_public_payroll_months_page(
  page_size integer default 24,
  before_month date default null
)
returns table (
  reference_month text,
  public_body_name text,
  employee_count integer,
  gross_amount numeric(20,2),
  deduction_amount numeric(20,2),
  net_amount numeric(20,2),
  subtotal_count integer,
  document_count integer,
  source_url text,
  artifact_sha256 text,
  source_retrieved_at timestamptz,
  parser_version text,
  source_documents jsonb
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 60 then
    raise exception 'limite de meses da folha invalido'
      using errcode = '22023';
  end if;

  if before_month is not null
     and before_month <> date_trunc('month', before_month)::date then
    raise exception 'cursor mensal da folha invalido'
      using errcode = '22023';
  end if;

  return query
  with current_components as (
    select
      aggregate.*,
      body.name as body_name,
      artifact.source_url as document_url,
      artifact.sha256 as document_sha256,
      artifact.retrieved_at as document_retrieved_at
    from hr.payroll_report_aggregates as aggregate
    join org.public_bodies as body on body.id = aggregate.public_body_id
    join raw.raw_artifacts as artifact
      on artifact.id = aggregate.source_document_artifact_id
    where aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
          -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
          -- não substitui a versão anterior.
          and not exists (
            select 1
            from hr.payroll_report_aggregate_invalidations as successor_invalidation
            where successor_invalidation.aggregate_id = successor.id
          )
      )
  ), monthly_totals as (
    select
      component.reference_month,
      component.public_body_id,
      max(component.body_name) as body_name,
      max(component.employee_count) filter (
        where component.payroll_cycle = 'regular'
      )::integer as regular_employee_count,
      sum(component.gross_amount)::numeric(20,2) as total_gross,
      sum(component.deduction_amount)::numeric(20,2) as total_deduction,
      sum(component.net_amount)::numeric(20,2) as total_net,
      sum(component.subtotal_count)::integer as total_subtotals,
      count(*)::integer as total_documents,
      (array_agg(
        component.document_url order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_url,
      (array_agg(
        component.document_sha256 order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_sha256,
      (array_agg(
        component.document_retrieved_at order by component.version desc
      ) filter (
        where component.payroll_cycle = 'regular'
      ))[1] as regular_document_retrieved_at,
      jsonb_agg(
        jsonb_build_object(
          'payroll_cycle', component.payroll_cycle,
          'source_url', component.document_url,
          'artifact_sha256', component.document_sha256,
          'source_retrieved_at', component.document_retrieved_at,
          'parser_version', component.parser_version
        ) order by case component.payroll_cycle
          when 'regular' then 1
          when 'thirteenth_advance' then 2
          when 'thirteenth_final' then 3
        end
      ) as documents
    from current_components as component
    group by component.reference_month, component.public_body_id
    having count(*) filter (
      where component.payroll_cycle = 'regular'
    ) = 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_advance'
      ) <= 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_final'
      ) <= 1
  ), target_months as (
    select distinct monthly.reference_month
    from monthly_totals as monthly
    where before_month is null or monthly.reference_month < before_month
    order by monthly.reference_month desc
    limit page_size
  )
  select
    to_char(monthly.reference_month, 'YYYY-MM-DD'),
    monthly.body_name,
    monthly.regular_employee_count,
    monthly.total_gross,
    monthly.total_deduction,
    monthly.total_net,
    monthly.total_subtotals,
    monthly.total_documents,
    monthly.regular_document_url,
    monthly.regular_document_sha256,
    monthly.regular_document_retrieved_at,
    'payroll-monthly-total/1.0.0'::text,
    monthly.documents
  from monthly_totals as monthly
  join target_months as target
    on target.reference_month = monthly.reference_month
  order by monthly.reference_month desc, monthly.public_body_id;
end;
$function$;

create or replace function hr.payroll_month_is_public(target_reference_month date)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    with current_components as (
      select aggregate.*
      from hr.payroll_report_aggregates as aggregate
      join org.public_bodies as public_body
        on public_body.id = aggregate.public_body_id
      where aggregate.reference_month = target_reference_month
        and public_body.ibge_code = '2903201'
        and public_body.body_type = 'executive'
        and aggregate.validation_state = 'validated'
        and not exists (
          select 1
          from hr.payroll_report_aggregate_invalidations as invalidation
          where invalidation.aggregate_id = aggregate.id
        )
        and not exists (
          select 1
          from hr.payroll_report_aggregates as successor
          where successor.supersedes_id = aggregate.id
            and successor.validation_state <> 'rejected'
            -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
            -- não substitui a versão anterior.
            and not exists (
              select 1
              from hr.payroll_report_aggregate_invalidations as successor_invalidation
              where successor_invalidation.aggregate_id = successor.id
            )
        )
    )
    select 1
    from current_components
    group by reference_month, public_body_id
    having count(*) filter (
      where payroll_cycle = 'regular'
    ) = 1
      and count(*) filter (
        where payroll_cycle = 'thirteenth_advance'
      ) <= 1
      and count(*) filter (
        where payroll_cycle = 'thirteenth_final'
      ) <= 1
  );
$function$;

create or replace function api.get_public_payroll_coverage(
  month_limit integer default 120
)
returns table (
  reference_month text,
  coverage_status text,
  coverage_note text,
  catalog_document_count integer,
  preserved_document_count integer,
  source_url text,
  artifact_sha256 text,
  catalog_checked_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if month_limit is null or month_limit < 1 or month_limit > 120 then
    raise exception 'limite de cobertura da folha invalido'
      using errcode = '22023';
  end if;

  return query
  with latest_complete_catalog as (
    select
      partition.collection_run_id,
      partition.completed_at,
      endpoint.id as endpoint_id
    from source.collection_partitions as partition
    join source.source_endpoints as endpoint
      on endpoint.id = partition.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and partition.partition_key like 'snapshot:servidores:%'
      and partition.status = 'complete'
      and partition.observed_records > 0
      and partition.collection_run_id is not null
      and partition.completed_at is not null
    order by partition.completed_at desc, partition.id desc
    limit 1
  ), catalog_evidence as (
    select
      catalog.collection_run_id,
      catalog.completed_at,
      coalesce(artifact.source_url, endpoint.base_url) as catalog_url
    from latest_complete_catalog as catalog
    join source.source_endpoints as endpoint on endpoint.id = catalog.endpoint_id
    left join lateral (
      select candidate.source_url
      from raw.raw_artifacts as candidate
      where candidate.collection_run_id = catalog.collection_run_id
        and candidate.source_endpoint_id = catalog.endpoint_id
        and candidate.artifact_kind = 'http_response'
        and candidate.source_url like 'https://%'
      order by candidate.retrieved_at desc, candidate.id desc
      limit 1
    ) as artifact on true
  ), exact_catalog_records as (
    select distinct on (record.source_record_key)
      record.id,
      record.source_record_key,
      record.payload,
      record.collected_at,
      origin_artifact.source_endpoint_id,
      make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) as reference_month
    from raw.raw_records as record
    join raw.raw_artifacts as origin_artifact
      on origin_artifact.id = record.raw_artifact_id
    join source.source_endpoints as endpoint
      on endpoint.id = origin_artifact.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and record.record_type = 'municipal_transparency_servidores'
      and record.payload ->> 'ano_ref' ~ '^(20[2-9][0-9]|2100)$'
      and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
      and make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) >= date '2021-01-01'
      and (
        (
          record.payload ->> 'tipo' = '1'
          and regexp_replace(
            btrim(translate(
              normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
              U&'\0300\0301\0302\0303\0308\0327',
              ''
            )),
            '[[:space:]]+', ' ', 'g'
          ) in (
            'relacao de servidores',
            'relacao servidores',
            'relacao de servidores 13o salario'
          )
        )
        or (
          coalesce(trim(record.payload ->> 'tipo'), '') = ''
          and regexp_replace(
            btrim(translate(
              normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
              U&'\0300\0301\0302\0303\0308\0327',
              ''
            )),
            '[[:space:]]+', ' ', 'g'
          ) = 'relacao de servidores'
        )
      )
    order by record.source_record_key, record.collected_at desc, record.id desc
  ), catalog_months as (
    select
      record.reference_month,
      count(*)::integer as document_count,
      (array_agg(
        record.payload ->> 'url'
        order by record.collected_at desc, record.id desc
      ))[1] as document_url
    from exact_catalog_records as record
    group by record.reference_month
  ), preserved_documents as (
    select distinct on (record.source_record_key)
      record.reference_month,
      record.source_record_key,
      document.id,
      document.source_url,
      document.sha256,
      document.retrieved_at
    from exact_catalog_records as record
    join raw.raw_artifacts as document
      on document.artifact_kind = 'document'
      and document.source_endpoint_id = record.source_endpoint_id
      and document.metadata ->> 'schema_name'
        = 'municipal-transparency-document'
      and document.metadata ->> 'source_record_key'
        = record.source_record_key
      and document.source_url = record.payload ->> 'url'
    order by
      record.source_record_key,
      document.retrieved_at desc,
      document.id desc
  ), preserved_months as (
    select
      document.reference_month,
      count(*)::integer as document_count,
      (array_agg(
        document.source_url
        order by document.retrieved_at desc, document.id desc
      ))[1] as document_url,
      (array_agg(
        document.sha256
        order by document.retrieved_at desc, document.id desc
      ))[1] as document_sha256
    from preserved_documents as document
    group by document.reference_month
  ), current_components as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    join org.public_bodies as public_body
      on public_body.id = aggregate.public_body_id
    where public_body.ibge_code = '2903201'
      and public_body.body_type = 'executive'
      and aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
          -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
          -- não substitui a versão anterior.
          and not exists (
            select 1
            from hr.payroll_report_aggregate_invalidations as successor_invalidation
            where successor_invalidation.aggregate_id = successor.id
          )
      )
  ), published_months as (
    select component.reference_month
    from current_components as component
    group by component.reference_month, component.public_body_id
    having count(*) filter (where component.payroll_cycle = 'regular') = 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_advance'
      ) <= 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_final'
      ) <= 1
  ), conflicted_months as (
    select distinct aggregate.reference_month
    from hr.payroll_report_aggregate_invalidations as invalidation
    join hr.payroll_report_aggregates as aggregate
      on aggregate.id = invalidation.aggregate_id
    join org.public_bodies as public_body
      on public_body.id = aggregate.public_body_id
    where public_body.ibge_code = '2903201'
      and public_body.body_type = 'executive'
      and invalidation.reason_code = 'mixed_payroll_cycle_header'
  ), latest_month as (
    select max(candidate.reference_month) as reference_month
    from (
      select catalog.reference_month from catalog_months as catalog
      union all
      select published.reference_month from published_months as published
      union all
      select conflict.reference_month from conflicted_months as conflict
    ) as candidate
  ), months as (
    select generated.reference_month::date
    from latest_month
    cross join lateral generate_series(
      date '2021-01-01',
      latest_month.reference_month,
      interval '1 month'
    ) as generated(reference_month)
    where latest_month.reference_month is not null
    order by generated.reference_month desc
    limit month_limit
  )
  select
    to_char(month.reference_month, 'YYYY-MM-DD'),
    case
      when published.reference_month is not null then 'published'
      when conflict.reference_month is not null then 'source_conflict'
      when catalog.reference_month is not null then 'processing_pending'
      else 'document_not_found'
    end,
    case
      when published.reference_month is not null then
        'Totais validados por código e publicados com o PDF oficial.'
      when conflict.reference_month is not null then
        'O documento oficial mistura ciclos da folha que não podem ser separados com segurança. Os valores ficam fora do total.'
      when catalog.reference_month is not null then
        'A fonte lista a folha oficial, mas o documento ainda não concluiu todas as validações determinísticas. Nenhum valor foi presumido.'
      else
        'A consulta completa ao catálogo oficial não localizou uma Relação de Servidores para esta competência. Isso não significa gasto zero.'
    end,
    coalesce(catalog.document_count, 0),
    coalesce(preserved.document_count, 0),
    case
      when catalog.reference_month is null then evidence.catalog_url
      else coalesce(preserved.document_url, catalog.document_url)
    end,
    preserved.document_sha256,
    evidence.completed_at,
    'payroll-coverage/1.0.0'::text
  from months as month
  cross join catalog_evidence as evidence
  left join catalog_months as catalog
    on catalog.reference_month = month.reference_month
  left join preserved_months as preserved
    on preserved.reference_month = month.reference_month
  left join published_months as published
    on published.reference_month = month.reference_month
  left join conflicted_months as conflict
    on conflict.reference_month = month.reference_month
  order by month.reference_month desc;
end;
$function$;

create or replace function hr.get_pending_payroll_regime_documents(
  requested_limit integer,
  target_reference_month date default null
)
returns table (
  aggregate_id text,
  artifact_id text,
  sha256 text,
  object_key text,
  byte_size bigint,
  parent_record_id text,
  source_url text,
  reference_month date
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if requested_limit is null or requested_limit < 1 or requested_limit > 20 then
    raise exception 'limite de detalhamentos da folha inválido'
      using errcode = '22023';
  end if;
  if target_reference_month is not null and (
    target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date
  ) then
    raise exception 'competência do detalhamento da folha inválida'
      using errcode = '22023';
  end if;

  return query
  select
    aggregate.id::text,
    artifact.id::text,
    artifact.sha256,
    artifact.object_key,
    artifact.byte_size,
    aggregate.origin_raw_record_id::text,
    artifact.source_url,
    aggregate.reference_month
  from hr.payroll_report_aggregates as aggregate
  join raw.raw_artifacts as artifact
    on artifact.id = aggregate.source_document_artifact_id
  where aggregate.report_kind = 'municipal_staff'
    and aggregate.validation_state = 'validated'
    and aggregate.parser_version = 'payroll-report-aggregate/1.4.0'
    and aggregate.reference_month = coalesce(
      target_reference_month,
      aggregate.reference_month
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregates as successor
      where successor.supersedes_id = aggregate.id
        and successor.validation_state <> 'rejected'
        -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
        -- não substitui a versão anterior.
        and not exists (
          select 1
          from hr.payroll_report_aggregate_invalidations as successor_invalidation
          where successor_invalidation.aggregate_id = successor.id
        )
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregate_invalidations as invalidation
      where invalidation.aggregate_id = aggregate.id
    )
    and not exists (
      select 1
      from hr.payroll_report_regime_breakdowns as breakdown
      where breakdown.payroll_report_aggregate_id = aggregate.id
        and breakdown.parser_version in (
    'payroll-regime-breakdown/1.0.0',
    'payroll-regime-breakdown/1.1.0',
    'payroll-regime-breakdown/1.2.0'
  )
    )
  order by aggregate.reference_month desc, aggregate.payroll_cycle,
    aggregate.id
  limit requested_limit;
end;
$function$;

create or replace function api.get_public_payroll_regime_breakdown(
  target_reference_month date
)
returns table (
  reference_month text,
  regime_code text,
  regime_label text,
  employee_count integer,
  gross_amount numeric(20,2),
  deduction_amount numeric(20,2),
  net_amount numeric(20,2),
  source_document_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if target_reference_month is null
    or target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date then
    raise exception 'competência do detalhamento da folha inválida'
      using errcode = '22023';
  end if;

  return query
  with current_components as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    where aggregate.reference_month = target_reference_month
      and aggregate.report_kind = 'municipal_staff'
      and aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
          -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
          -- não substitui a versão anterior.
          and not exists (
            select 1
            from hr.payroll_report_aggregate_invalidations as successor_invalidation
            where successor_invalidation.aggregate_id = successor.id
          )
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
  ), complete_components as (
    select component.*, breakdown.categories
    from current_components as component
    join hr.payroll_report_regime_breakdowns as breakdown
      on breakdown.payroll_report_aggregate_id = component.id
     and breakdown.parser_version in (
    'payroll-regime-breakdown/1.0.0',
    'payroll-regime-breakdown/1.1.0',
    'payroll-regime-breakdown/1.2.0'
  )
    where (select count(*) from current_components)
      = (select count(*)
           from current_components as expected
           join hr.payroll_report_regime_breakdowns as available
             on available.payroll_report_aggregate_id = expected.id
            and available.parser_version in (
    'payroll-regime-breakdown/1.0.0',
    'payroll-regime-breakdown/1.1.0',
    'payroll-regime-breakdown/1.2.0'
  ))
      and (select count(*) from current_components) > 0
  ), expanded as (
    select
      component.reference_month,
      component.id as component_id,
      component.payroll_cycle,
      item ->> 'regime_code' as regime_code,
      item ->> 'regime_label' as regime_label,
      (item ->> 'employee_count')::integer as employee_count,
      (item ->> 'gross_amount')::numeric(20,2) as gross_amount,
      (item ->> 'deduction_amount')::numeric(20,2) as deduction_amount,
      (item ->> 'net_amount')::numeric(20,2) as net_amount
    from complete_components as component
    cross join lateral jsonb_array_elements(component.categories) as item
  )
  select
    to_char(expanded.reference_month, 'YYYY-MM-DD'),
    expanded.regime_code,
    max(expanded.regime_label),
    sum(
      case when expanded.payroll_cycle = 'regular'
        then expanded.employee_count else 0 end
    )::integer,
    sum(expanded.gross_amount)::numeric(20,2),
    sum(expanded.deduction_amount)::numeric(20,2),
    sum(expanded.net_amount)::numeric(20,2),
    (select count(*) from complete_components)::integer,
    'payroll-regime-monthly/1.0.0'::text
  from expanded
  group by expanded.reference_month, expanded.regime_code
  order by sum(expanded.gross_amount) desc, expanded.regime_code;
end;
$function$;

create or replace function hr.get_pending_payroll_compensation_documents(
  requested_limit integer,
  target_reference_month date default null
)
returns table (
  aggregate_id text,
  artifact_id text,
  sha256 text,
  object_key text,
  byte_size bigint,
  parent_record_id text,
  source_url text,
  reference_month date
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if requested_limit is null or requested_limit < 1 or requested_limit > 20 then
    raise exception 'limite de distribuições da folha inválido'
      using errcode = '22023';
  end if;
  if target_reference_month is not null and (
    target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date
  ) then
    raise exception 'competência da distribuição da folha inválida'
      using errcode = '22023';
  end if;

  return query
  select
    aggregate.id::text,
    artifact.id::text,
    artifact.sha256,
    artifact.object_key,
    artifact.byte_size,
    aggregate.origin_raw_record_id::text,
    artifact.source_url,
    aggregate.reference_month
  from hr.payroll_report_aggregates as aggregate
  join raw.raw_artifacts as artifact
    on artifact.id = aggregate.source_document_artifact_id
  where aggregate.report_kind = 'municipal_staff'
    and aggregate.payroll_cycle = 'regular'
    and aggregate.validation_state = 'validated'
    and aggregate.parser_version = 'payroll-report-aggregate/1.4.0'
    and aggregate.reference_month = coalesce(
      target_reference_month,
      aggregate.reference_month
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregates as successor
      where successor.supersedes_id = aggregate.id
        and successor.validation_state <> 'rejected'
        -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
        -- não substitui a versão anterior.
        and not exists (
          select 1
          from hr.payroll_report_aggregate_invalidations as successor_invalidation
          where successor_invalidation.aggregate_id = successor.id
        )
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregate_invalidations as invalidation
      where invalidation.aggregate_id = aggregate.id
    )
    and not exists (
      select 1
      from hr.payroll_report_compensation_distributions as distribution
      where distribution.payroll_report_aggregate_id = aggregate.id
        and distribution.parser_version in (
    'payroll-compensation-bands/1.0.0',
    'payroll-compensation-bands/1.1.0'
  )
    )
  order by aggregate.reference_month desc, aggregate.id
  limit requested_limit;
end;
$function$;

create or replace function api.get_public_payroll_compensation_distribution(
  target_reference_month date
)
returns table (
  reference_month text,
  band_code text,
  band_label text,
  employee_count integer,
  gross_amount numeric(20,2),
  average_gross_amount numeric(20,2),
  maximum_gross_amount numeric(20,2),
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if target_reference_month is null
    or target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date then
    raise exception 'competência da distribuição da folha inválida'
      using errcode = '22023';
  end if;

  return query
  with current_regular as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    where aggregate.reference_month = target_reference_month
      and aggregate.report_kind = 'municipal_staff'
      and aggregate.payroll_cycle = 'regular'
      and aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
          -- Sucessor invalidado (ex.: competência declarada no PDF diverge)
          -- não substitui a versão anterior.
          and not exists (
            select 1
            from hr.payroll_report_aggregate_invalidations as successor_invalidation
            where successor_invalidation.aggregate_id = successor.id
          )
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
  ), available as (
    select aggregate.*, distribution.bands,
      distribution.maximum_gross_amount
    from current_regular as aggregate
    join hr.payroll_report_compensation_distributions as distribution
      on distribution.payroll_report_aggregate_id = aggregate.id
     and distribution.parser_version in (
    'payroll-compensation-bands/1.0.0',
    'payroll-compensation-bands/1.1.0'
  )
    where (select count(*) from current_regular) = 1
  )
  select
    to_char(available.reference_month, 'YYYY-MM-DD'),
    item ->> 'band_code',
    item ->> 'band_label',
    (item ->> 'employee_count')::integer,
    (item ->> 'gross_amount')::numeric(20,2),
    round(available.gross_amount / available.employee_count, 2)::numeric(20,2),
    available.maximum_gross_amount,
    'payroll-compensation-monthly/1.0.0'::text
  from available
  cross join lateral jsonb_array_elements(available.bands) as item
  order by case item ->> 'band_code'
    when 'up_to_1500' then 1
    when 'from_1500_01_to_3000' then 2
    when 'from_3000_01_to_5000' then 3
    when 'from_5000_01_to_10000' then 4
    when 'from_10000_01_to_20000' then 5
    when 'above_20000' then 6
  end;
end;
$function$;

notify pgrst, 'reload schema';

commit;
