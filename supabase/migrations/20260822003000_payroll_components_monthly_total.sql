begin;

-- Um mesmo mês pode ter folha regular, adiantamento do 13º e 13º final.
-- Esses documentos são componentes financeiros, não retificações entre si.
alter table hr.payroll_report_aggregates
  add column payroll_cycle text not null default 'regular'
  constraint payroll_report_aggregates_cycle_allowed check (
    payroll_cycle in (
      'regular',
      'thirteenth_advance',
      'thirteenth_final'
    )
  );

alter table hr.payroll_report_aggregates
  drop constraint payroll_report_aggregates_supersedes_same_series;
alter table hr.payroll_report_aggregates
  drop constraint payroll_report_aggregates_identity_unique;

alter table hr.payroll_report_aggregates
  add constraint payroll_report_aggregates_identity_unique
  unique (
    id, public_body_id, report_kind, reference_month, payroll_cycle
  );
alter table hr.payroll_report_aggregates
  add constraint payroll_report_aggregates_supersedes_same_series
  foreign key (
    supersedes_id, public_body_id, report_kind, reference_month, payroll_cycle
  ) references hr.payroll_report_aggregates (
    id, public_body_id, report_kind, reference_month, payroll_cycle
  );

drop index hr.payroll_report_aggregates_supersedes_series_idx;
create index payroll_report_aggregates_supersedes_series_idx
  on hr.payroll_report_aggregates (
    supersedes_id, public_body_id, report_kind, reference_month, payroll_cycle
  );

drop index hr.payroll_report_aggregates_series_version_unique_idx;
create unique index payroll_report_aggregates_series_version_unique_idx
on hr.payroll_report_aggregates (
  public_body_id, report_kind, reference_month, payroll_cycle, version
);

drop function api.get_public_payroll_months(integer);

create function api.get_public_payroll_months(page_size integer default 24)
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

revoke all on function api.get_public_payroll_months(integer) from public;
grant execute on function api.get_public_payroll_months(integer)
  to anon, authenticated;

comment on column hr.payroll_report_aggregates.payroll_cycle is
  'Processamento identificado no cabeçalho oficial: regular, adiantamento do 13º ou 13º final.';
comment on function api.get_public_payroll_months(integer) is
  'Total mensal determinístico dos componentes vigentes da folha. Quantidade de vínculos vem somente da folha regular e cada PDF permanece citado.';

notify pgrst, 'reload schema';

commit;
