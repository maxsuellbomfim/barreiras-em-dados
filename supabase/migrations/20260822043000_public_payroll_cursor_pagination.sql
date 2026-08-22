begin;

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

revoke all on function api.get_public_payroll_months_page(integer,date)
  from public;
grant execute on function api.get_public_payroll_months_page(integer,date)
  to anon, authenticated;

comment on function api.get_public_payroll_months_page(integer,date) is
  'Pagina por competência, em ordem decrescente e com cursor mensal exclusivo, os totais determinísticos vigentes da folha sem truncar o histórico.';

notify pgrst, 'reload schema';

commit;
