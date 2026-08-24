begin;

create function api.get_public_siconfi_monthly_reconciliation(
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  fiscal_year smallint,
  metric_key text,
  annual_amount text,
  monthly_sum_amount text,
  difference_amount text,
  observed_months smallint,
  missing_months smallint[],
  reconciliation_status text,
  reconciliation_note text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if fiscal_year_from < 1988
     or fiscal_year_from > effective_year_to
     or effective_year_to > 2200
     or effective_year_to - fiscal_year_from > 20 then
    raise exception 'intervalo fiscal inválido'
      using errcode = '22023';
  end if;

  return query
  with annual as materialized (
    select
      total.fiscal_year,
      total.metric_key,
      total.amount
    from finance.siconfi_annual_totals as total
    where total.validation_status = 'validated'
      and total.fiscal_year between fiscal_year_from and effective_year_to
      and total.metric_key in (
        'expense_committed', 'expense_liquidated', 'expense_paid'
      )
      and not exists (
        select 1
        from finance.siconfi_annual_totals as successor
        where successor.supersedes_id = total.id
      )
      and exists (
        select 1
        from evidence.evidence_items as evidence_item
        where evidence_item.target_type = 'finance.siconfi_annual_totals'
          and evidence_item.target_id = total.id
          and evidence_item.raw_record_id = total.origin_raw_record_id
          and evidence_item.raw_artifact_id = total.source_artifact_id
          and evidence_item.is_primary
      )
  ),
  monthly_values as materialized (
    select
      closure.fiscal_year,
      extract(month from closure.period_start)::smallint as month_number,
      metric.metric_key,
      metric.amount
    from api.get_public_monthly_finance_closures(
      120, null::smallint
    ) as closure
    cross join lateral (
      values
        ('expense_committed'::text, closure.expense_committed_amount),
        ('expense_liquidated'::text, closure.expense_liquidated_amount),
        ('expense_paid'::text, closure.expense_paid_amount)
    ) as metric(metric_key, amount)
    where closure.fiscal_year between fiscal_year_from and effective_year_to
  ),
  monthly_coverage as materialized (
    select
      annual_record.fiscal_year,
      annual_record.metric_key,
      annual_record.amount as annual_amount,
      count(distinct monthly.month_number) filter (
        where monthly.amount is not null
      )::smallint as observed_months,
      sum(monthly.amount) filter (
        where monthly.amount is not null
      ) as monthly_sum,
      coalesce(
        array_agg(month.month_number order by month.month_number) filter (
          where not exists (
            select 1
            from monthly_values as observed
            where observed.fiscal_year = annual_record.fiscal_year
              and observed.metric_key = annual_record.metric_key
              and observed.month_number = month.month_number
              and observed.amount is not null
          )
        ),
        array[]::smallint[]
      ) as missing_months
    from annual as annual_record
    cross join lateral (
      select generated_month::smallint as month_number
      from generate_series(1, 12) as generated_month
    ) as month
    left join monthly_values as monthly
      on monthly.fiscal_year = annual_record.fiscal_year
     and monthly.metric_key = annual_record.metric_key
     and monthly.month_number = month.month_number
    group by
      annual_record.fiscal_year,
      annual_record.metric_key,
      annual_record.amount
  )
  select
    coverage.fiscal_year,
    coverage.metric_key,
    coverage.annual_amount::text,
    case
      when coverage.observed_months = 12 then coverage.monthly_sum::text
    end,
    case
      when coverage.observed_months = 12
      then (coverage.annual_amount - coverage.monthly_sum)::text
    end,
    coverage.observed_months,
    coverage.missing_months,
    case
      when coverage.observed_months < 12 then 'incomplete_months'
      when coverage.annual_amount = coverage.monthly_sum then 'matched_exact'
      else 'source_difference'
    end,
    case
      when coverage.observed_months < 12
        then 'A série mensal não cobre os doze meses; nenhum total parcial foi comparado com a declaração anual.'
      when coverage.annual_amount = coverage.monthly_sum
        then 'A soma dos doze relatórios mensais confere exatamente com a declaração anual do SICONFI.'
      else 'As duas fontes oficiais publicam valores diferentes. Isso pode refletir ajustes de encerramento e não prova irregularidade.'
    end,
    'siconfi-monthly-reconciliation/1.0.0'::text
  from monthly_coverage as coverage
  order by coverage.fiscal_year desc, coverage.metric_key;
end;
$function$;

revoke all on function api.get_public_siconfi_monthly_reconciliation(
  smallint, smallint
) from public;
grant execute on function api.get_public_siconfi_monthly_reconciliation(
  smallint, smallint
) to anon, authenticated;

comment on function api.get_public_siconfi_monthly_reconciliation(
  smallint, smallint
) is
  'Compara somente os três estágios anuais de despesa com doze valores mensais disponíveis; anos incompletos não são somados.';

notify pgrst, 'reload schema';

commit;
