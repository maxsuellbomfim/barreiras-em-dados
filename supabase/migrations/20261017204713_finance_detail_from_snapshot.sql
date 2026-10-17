begin;

-- O detalhe mensal (/financas/AAAA-MM) recalculava o fechamento 1.2.0 ao
-- vivo e passou dos 3 s do papel anônimo depois de #932 (erro 500 e página
-- "Consulta temporariamente indisponível" em 17/10/2026). O detalhe passa a
-- ler o fechamento do instantâneo por ano, e o fechamento só calcula a parcela
-- do Legislativo nas competências que também têm a prestação ao TCM-BA (as
-- únicas em que ela é usada). Mesmo resultado.
create or replace function api.get_public_monthly_finance_closures_calculated(
  page_size integer default 24,
  fiscal_year_filter smallint default null
)
returns table (
  closure_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_amount numeric,
  revenue_report_count integer,
  revenue_line_count integer,
  expense_paid_amount numeric,
  expense_committed_amount numeric,
  expense_liquidated_amount numeric,
  expense_report_count integer,
  operational_difference_amount numeric,
  closure_status text,
  coverage_note text,
  calculation_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
set work_mem = '16MB'
as $function$
#variable_conflict use_column
begin
  if page_size < 1 or page_size > 120 then
    raise exception 'page_size deve estar entre 1 e 120'
      using errcode = '22023';
  end if;

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;
  return query
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  revenue_current as (
    select *
    from (
      select
        revenue.*,
        row_number() over (
          partition by revenue.public_body_id,
            coalesce(revenue.external_id, revenue.id::text)
          order by revenue.version desc, revenue.created_at desc,
            revenue.id desc
        ) as current_row
      from finance.revenues as revenue
      join exact_lineage as lineage
        on lineage.origin_raw_record_id = revenue.origin_raw_record_id
       and lineage.document_artifact_id = revenue.source_document_artifact_id
      where revenue.validation_status = 'validated'
        and revenue.published_at is not null
        and revenue.revenue_date is not null
        and revenue.source_document_artifact_id is not null
        and (
          fiscal_year_filter is null
          or revenue.fiscal_year = fiscal_year_filter
        )
    ) as versioned_revenue
    where versioned_revenue.current_row = 1
  ),
  revenue_source_reports as (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      revenue.source_document_artifact_id,
      max(revenue.report_total_period_amount) as report_amount,
      count(*)::integer as line_count
    from revenue_current as revenue
    group by
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date,
      revenue.source_document_artifact_id
  ),
  -- 1.2.0: relatórios com o mesmo total declarado são o mesmo demonstrativo
  -- publicado por mais de uma fonte oficial (portal e TCM-BA) e contam uma vez.
  revenue_months as (
    select
      source.public_body_id,
      source.period_start,
      case when count(distinct source.report_amount) = 1
        then max(source.report_amount)
        else sum(source.report_amount) end as report_amount,
      count(distinct source.report_amount)::integer as report_count,
      case when count(distinct source.report_amount) = 1
        then max(source.line_count)
        else sum(source.line_count) end::integer as line_count
    from revenue_source_reports as source
    group by source.public_body_id, source.period_start
  ),
  expense_current as (
    select distinct on (
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id
    )
      report.*
    from finance.expense_reports as report
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.document_artifact_id = report.source_document_artifact_id
    where report.validation_status = 'validated'
      and report.published_at is not null
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
    order by
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id,
      report.version desc,
      report.created_at desc,
      report.id desc
  ),
  -- Só competências que também têm a prestação ao TCM-BA precisam da parcela
  -- do Legislativo (13/10/2026: somar todas as linhas de todos os meses
  -- deixava o detalhe mensal acima de 3 s).
  tcm_months as (
    select distinct expense.public_body_id,
      date_trunc('month', expense.period_end)::date as period_start
    from expense_current as expense
    where expense.methodology_version like 'tcm-ba-%'
  ),
  -- Parcela do Poder Legislativo (órgão 01) no demonstrativo consolidado do
  -- portal, pela alocação vigente de cada linha à unidade orçamentária.
  legislative_lines as (
    select expense.id as report_id,
      sum(line.paid_period_amount) as paid_amount,
      sum(line.committed_period_amount) as committed_amount,
      sum(line.liquidated_period_amount) as liquidated_amount
    from expense_current as expense
    join finance.expense_lines as line
      on line.report_id = expense.id
     and line.origin_raw_record_id = expense.origin_raw_record_id
    join lateral (
      select allocation.budget_unit_code
      from finance.expense_line_budget_units as allocation
      where allocation.expense_line_id = line.id
        and allocation.source_document_artifact_id = expense.source_document_artifact_id
        and allocation.origin_raw_record_id = expense.origin_raw_record_id
      order by allocation.version desc, allocation.created_at desc, allocation.id desc
      limit 1
    ) as unit on true
    where expense.methodology_version like 'public-expense-pdf/%'
      and unit.budget_unit_code like '01%'
      and exists (
        select 1 from tcm_months
        where tcm_months.public_body_id = expense.public_body_id
          and tcm_months.period_start = date_trunc('month', expense.period_end)::date
      )
    group by expense.id
  ),
  expense_statements as (
    select
      expense.public_body_id,
      date_trunc('month', expense.period_end)::date as period_start,
      expense.period_end,
      expense.methodology_version like 'tcm-ba-%' as is_tcm,
      expense.total_paid_period_amount as paid_amount,
      expense.total_committed_period_amount as committed_amount,
      expense.total_liquidated_period_amount as liquidated_amount,
      expense.total_paid_period_amount - coalesce(legislative.paid_amount, 0)
        as executive_paid_amount,
      expense.total_committed_period_amount - coalesce(legislative.committed_amount, 0)
        as executive_committed_amount,
      expense.total_liquidated_period_amount - coalesce(legislative.liquidated_amount, 0)
        as executive_liquidated_amount
    from expense_current as expense
    left join legislative_lines as legislative on legislative.report_id = expense.id
  ),
  expense_grouped as (
    select
      statement.public_body_id,
      statement.period_start,
      max(statement.period_end)::date as period_end,
      count(distinct (statement.paid_amount, statement.committed_amount,
        statement.liquidated_amount)) filter (where not statement.is_tcm)
        as portal_count,
      count(distinct (statement.paid_amount, statement.committed_amount,
        statement.liquidated_amount)) filter (where statement.is_tcm)
        as tcm_count,
      max(statement.paid_amount) filter (where not statement.is_tcm) as portal_paid,
      max(statement.committed_amount) filter (where not statement.is_tcm) as portal_committed,
      max(statement.liquidated_amount) filter (where not statement.is_tcm) as portal_liquidated,
      max(statement.executive_paid_amount) filter (where not statement.is_tcm) as portal_executive_paid,
      max(statement.executive_committed_amount) filter (where not statement.is_tcm) as portal_executive_committed,
      max(statement.executive_liquidated_amount) filter (where not statement.is_tcm) as portal_executive_liquidated,
      max(statement.paid_amount) filter (where statement.is_tcm) as tcm_paid,
      max(statement.committed_amount) filter (where statement.is_tcm) as tcm_committed,
      max(statement.liquidated_amount) filter (where statement.is_tcm) as tcm_liquidated,
      max(statement.paid_amount) as any_paid,
      max(statement.committed_amount) as any_committed,
      max(statement.liquidated_amount) as any_liquidated
    from expense_statements as statement
    group by statement.public_body_id, statement.period_start
  ),
  -- Escopo: o portal publica a despesa consolidada (inclui a Câmara); a
  -- prestação ao TCM-BA, só a do Executivo. Com as duas, o portal vale quando,
  -- sem o órgão 01, confere ao centavo com o TCM-BA nos três totais.
  expense_months as (
    select
      grouped.public_body_id,
      grouped.period_start,
      grouped.period_end,
      case
        when grouped.portal_count = 1 and grouped.tcm_count = 0 then 'consolidated'
        when grouped.portal_count = 1 and grouped.tcm_count = 1
          and grouped.portal_executive_paid = grouped.tcm_paid
          and grouped.portal_executive_committed = grouped.tcm_committed
          and grouped.portal_executive_liquidated = grouped.tcm_liquidated
          then 'consolidated_checked'
        when grouped.portal_count = 0 and grouped.tcm_count = 1 then 'executive'
        else 'ambiguous'
      end as scope,
      grouped.portal_count + grouped.tcm_count as statement_count,
      grouped.portal_paid, grouped.portal_committed, grouped.portal_liquidated,
      grouped.tcm_paid, grouped.tcm_committed, grouped.tcm_liquidated,
      grouped.any_paid, grouped.any_committed, grouped.any_liquidated
    from expense_grouped as grouped
  ),
  expense_resolved as (
    select
      month.public_body_id,
      month.period_start,
      month.scope,
      case when month.scope = 'ambiguous' then month.statement_count::integer else 1 end
        as report_count,
      case month.scope
        when 'executive' then month.tcm_paid
        when 'ambiguous' then month.any_paid
        else month.portal_paid end as paid_amount,
      case month.scope
        when 'executive' then month.tcm_committed
        when 'ambiguous' then month.any_committed
        else month.portal_committed end as committed_amount,
      case month.scope
        when 'executive' then month.tcm_liquidated
        when 'ambiguous' then month.any_liquidated
        else month.portal_liquidated end as liquidated_amount
    from expense_months as month
  ),
  periods as (
    select public_body_id, period_start from revenue_months
    union
    select public_body_id, period_start from expense_resolved
  )
  select
    periods.public_body_id::text || ':' || periods.period_start::text,
    extract(year from periods.period_start)::smallint,
    periods.period_start,
    (periods.period_start + interval '1 month - 1 day')::date,
    body.name,
    revenue.report_amount,
    coalesce(revenue.report_count, 0),
    coalesce(revenue.line_count, 0),
    expense.paid_amount,
    expense.committed_amount,
    expense.liquidated_amount,
    coalesce(expense.report_count, 0),
    case
      when revenue.report_count = 1 and expense.report_count = 1
        then revenue.report_amount - expense.paid_amount
      else null
    end,
    case
      when revenue.report_count is null or expense.report_count is null
        then 'needs_data'::text
      when revenue.report_count > 1 or expense.report_count > 1
        then 'needs_review'::text
      else 'operational'::text
    end,
    case
      when revenue.report_count is null
        then 'Há pagamentos publicados, mas ainda não há relatório de receita comparável.'
      when expense.report_count is null
        then 'Há receita publicada, mas ainda não há relatório de pagamentos comparável.'
      when revenue.report_count > 1 or expense.report_count > 1
        then 'Há mais de um relatório na mesma competência; o total aguarda reconciliação para evitar dupla contagem.'
      else 'Diferença entre a receita total declarada no relatório e o pagamento efetivado no mês. Não é superávit fiscal. '
        || case expense.scope
          when 'consolidated_checked'
            then 'Pagamentos consolidados do município (inclui a Câmara Municipal); sem a Câmara, conferem ao centavo com a prestação de contas ao TCM-BA.'
          when 'executive'
            then 'Pagamentos só do Executivo, conforme a prestação de contas ao TCM-BA; a Câmara Municipal não está incluída.'
          else 'Pagamentos consolidados do município (inclui a Câmara Municipal).'
        end
    end,
    'monthly-finance-closure/1.2.0'::text
  from periods
  join org.public_bodies as body on body.id = periods.public_body_id
  left join revenue_months as revenue
    on revenue.public_body_id = periods.public_body_id
   and revenue.period_start = periods.period_start
  left join expense_resolved as expense
    on expense.public_body_id = periods.public_body_id
   and expense.period_start = periods.period_start
  order by periods.period_start desc, body.name
  limit page_size;
end;
$function$;

create or replace function api.get_public_monthly_finance_detail(
  period_filter date
)
returns table (
  closure_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_amount numeric,
  revenue_report_count integer,
  revenue_line_count integer,
  expense_paid_amount numeric,
  expense_committed_amount numeric,
  expense_liquidated_amount numeric,
  expense_report_count integer,
  operational_difference_amount numeric,
  closure_status text,
  coverage_note text,
  calculation_methodology text,
  revenue_documents jsonb,
  expense_documents jsonb,
  evidence_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if period_filter is null then
    raise exception 'period_filter e obrigatorio'
      using errcode = '22004';
  end if;

  if period_filter <> date_trunc('month', period_filter)::date then
    raise exception 'period_filter deve ser o primeiro dia do mes'
      using errcode = '22023';
  end if;

  if extract(year from period_filter) < 1900
     or extract(year from period_filter) > 2200 then
    raise exception 'period_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  -- Fechamento lido do instantâneo por ano (17/10/2026: recalcular a 1.2.0
  -- aqui passava dos 3 s do papel anônimo).
  with closure as materialized (
    select calculated.*
    from api.get_public_monthly_finance_closures(
      120,
      extract(year from period_filter)::smallint
    ) as calculated
    where calculated.period_start = period_filter
  ),
  revenue_current as materialized (
    select versioned.*
    from (
      select
        revenue.*,
        row_number() over (
          partition by revenue.public_body_id,
            coalesce(revenue.external_id, revenue.id::text)
          order by revenue.version desc, revenue.created_at desc,
            revenue.id desc
        ) as current_row
      from finance.revenues as revenue
      where revenue.validation_status = 'validated'
        and revenue.published_at is not null
        and revenue.revenue_date is not null
        and revenue.source_document_artifact_id is not null
        and date_trunc('month', revenue.revenue_date)::date = period_filter
        and finance.has_exact_document_lineage(
          revenue.origin_raw_record_id,
          revenue.source_document_artifact_id
        )
    ) as versioned
    where versioned.current_row = 1
  ),
  revenue_document_rows as materialized (
    select
      revenue.public_body_id,
      revenue.source_document_artifact_id,
      document.source_url as document_url,
      document.sha256 as artifact_sha256,
      source_artifact.source_url,
      source_artifact.sha256 as source_artifact_sha256,
      count(*)::integer as line_count,
      max(revenue.report_total_period_amount) as report_amount
    from revenue_current as revenue
    join raw.raw_records as origin
      on origin.id = revenue.origin_raw_record_id
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = revenue.source_document_artifact_id
    group by revenue.public_body_id,
      revenue.source_document_artifact_id,
      document.source_url,
      document.sha256,
      source_artifact.source_url,
      source_artifact.sha256
  ),
  revenue_evidence as materialized (
    select
      rows.public_body_id,
      jsonb_agg(
        jsonb_build_object(
          'document_url', rows.document_url,
          'artifact_sha256', rows.artifact_sha256,
          'source_url', rows.source_url,
          'source_artifact_sha256', rows.source_artifact_sha256,
          'line_count', rows.line_count,
          'report_amount', rows.report_amount::text
        )
        order by rows.artifact_sha256
      ) as documents
    from revenue_document_rows as rows
    group by rows.public_body_id
  ),
  expense_current as materialized (
    select ranked.*
    from (
      select
        report.*,
        row_number() over (
          partition by report.source_document_artifact_id
          order by report.version desc, report.created_at desc,
            report.id desc
        ) as current_row
      from finance.expense_reports as report
      where report.validation_status = 'validated'
        and report.published_at is not null
        and report.source_document_artifact_id is not null
        and date_trunc('month', report.period_end)::date = period_filter
        and finance.has_exact_document_lineage(
          report.origin_raw_record_id,
          report.source_document_artifact_id
        )
    ) as ranked
    where ranked.current_row = 1
  ),
  expense_evidence as materialized (
    select
      report.public_body_id,
      jsonb_agg(
        jsonb_build_object(
          'document_url', document.source_url,
          'artifact_sha256', document.sha256,
          'source_url', source_artifact.source_url,
          'source_artifact_sha256', source_artifact.sha256,
          'committed_amount', report.total_committed_period_amount::text,
          'liquidated_amount', report.total_liquidated_period_amount::text,
          'paid_amount', report.total_paid_period_amount::text
        )
        order by document.sha256
      ) as documents
    from expense_current as report
    join raw.raw_records as origin
      on origin.id = report.origin_raw_record_id
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = report.source_document_artifact_id
    group by report.public_body_id
  )
  select
    closure.closure_id,
    closure.fiscal_year,
    closure.period_start,
    closure.period_end,
    closure.public_body_name,
    closure.revenue_report_amount,
    closure.revenue_report_count,
    closure.revenue_line_count,
    closure.expense_paid_amount,
    closure.expense_committed_amount,
    closure.expense_liquidated_amount,
    closure.expense_report_count,
    closure.operational_difference_amount,
    closure.closure_status,
    closure.coverage_note,
    closure.calculation_methodology,
    coalesce(revenue.documents, '[]'::jsonb),
    coalesce(expense.documents, '[]'::jsonb),
    'public-monthly-finance-detail/1.0.0'::text
  from closure
  left join revenue_evidence as revenue
    on closure.closure_id = revenue.public_body_id::text
      || ':' || period_filter::text
  left join expense_evidence as expense
    on closure.closure_id = expense.public_body_id::text
      || ':' || period_filter::text;
end;
$function$;

notify pgrst, 'reload schema';

commit;
