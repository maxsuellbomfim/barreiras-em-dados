begin;

-- Fechamento mensal 1.2.0 e cobertura 1.2.0 (ADR 0098, 13/10/2026).
-- Com a extração do TCM-BA chegando a 2022, cada competência passou a ter
-- dois demonstrativos oficiais: o do portal da Prefeitura e o da prestação de
-- contas ao TCM-BA. A 1.1.0 tratava isso como dupla contagem: janeiro e
-- fevereiro de 2022 ficaram em revisão e com a receita somada em dobro.
-- - Receita: relatórios com o mesmo total declarado são o mesmo demonstrativo
--   e contam uma vez (as duas fontes coincidem ao centavo).
-- - Despesa: o portal publica a despesa consolidada (inclui a Câmara
--   Municipal); a prestação ao TCM-BA, só a do Executivo. Com as duas, vale o
--   portal quando, sem o órgão 01 (Legislativo), confere ao centavo com o
--   TCM-BA em pago, empenhado e liquidado; senão, segue em revisão.
-- - A nota de cada mês diz o escopo: consolidado (com a Câmara) ou só o
--   Executivo (meses que só têm a prestação ao TCM-BA, como 2021).
-- - A cobertura conta os demonstrativos reconciliados do fechamento.
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

create or replace function api.get_public_finance_coverage_calculated(
  page_size integer default 120,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  coverage_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_count integer,
  expense_report_count integer,
  coverage_status text,
  coverage_note text,
  calculation_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
set work_mem = '16MB'
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if page_size < 1 or page_size > 240 then
    raise exception 'page_size deve estar entre 1 e 240'
      using errcode = '22023';
  end if;

  if fiscal_year_from < 1900 or fiscal_year_from > effective_year_to
     or effective_year_to > 2200 then
    raise exception 'intervalo fiscal inválido'
      using errcode = '22023';
  end if;

  return query
  with bodies as (
    select distinct on (body.id)
      body.id,
      body.name
    from org.public_bodies as body
    where body.body_type = 'executive'
    order by body.id, body.version desc, body.created_at desc
  ),
  months as (
    select generate_series(
      make_date(fiscal_year_from, 1, 1),
      least(
        make_date(effective_year_to, 12, 1),
        date_trunc('month', current_date)::date
      ),
      interval '1 month'
    )::date as period_start
  ),
  -- Contagens de demonstrativos já reconciliadas pelo fechamento mensal
  -- (servido pelo instantâneo); zero vira ausência.
  closure_counts as materialized (
    select
      split_part(closure.closure_id, ':', 1)::uuid as public_body_id,
      closure.period_start,
      nullif(closure.revenue_report_count, 0) as revenue_count,
      nullif(closure.expense_report_count, 0) as expense_count
    from api.get_public_monthly_finance_closures(120, null::smallint) as closure
  )
  select
    body.id::text || ':' || months.period_start::text,
    extract(year from months.period_start)::smallint,
    months.period_start,
    (months.period_start + interval '1 month - 1 day')::date,
    body.name,
    coalesce(counts.revenue_count, 0),
    coalesce(counts.expense_count, 0),
    case
      when coalesce(counts.revenue_count, 0) > 1
        or coalesce(counts.expense_count, 0) > 1
        then 'needs_review'::text
      when counts.revenue_count is not null and counts.expense_count is not null
        then 'complete'::text
      when counts.revenue_count is not null
        then 'revenue_only'::text
      when counts.expense_count is not null
        then 'expense_only'::text
      else 'missing'::text
    end,
    case
      when coalesce(counts.revenue_count, 0) > 1
        or coalesce(counts.expense_count, 0) > 1
        then 'Há mais de um relatório na competência; a leitura aguarda reconciliação para evitar dupla contagem.'
      when counts.revenue_count is not null and counts.expense_count is not null
        then 'Há pelo menos um relatório validado de receita e um de despesa para este mês.'
      when counts.revenue_count is not null
        then 'Há receita validada, mas ainda não há relatório de despesa comparável.'
      when counts.expense_count is not null
        then 'Há despesa validada, mas ainda não há relatório de receita comparável.'
      else 'Nenhum relatório financeiro validado foi publicado para este mês; isso não significa receita ou despesa zero.'
    end,
    'finance-coverage/1.2.0'::text
  from bodies as body
  cross join months
  left join closure_counts as counts
    on counts.public_body_id = body.id
   and counts.period_start = months.period_start
  order by months.period_start desc, body.name
  limit page_size;
end;
$function$;

notify pgrst, 'reload schema';

commit;