begin;

create function hr.payroll_month_is_public(target_reference_month date)
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

revoke all on function hr.payroll_month_is_public(date) from public;
grant execute on function hr.payroll_month_is_public(date) to collector_worker;

comment on function hr.payroll_month_is_public(date) is
  'Confirma para o worker, sem expor tabelas internas, se a folha do Executivo de Barreiras satisfaz o mesmo contrato determinístico da projeção pública.';

commit;
