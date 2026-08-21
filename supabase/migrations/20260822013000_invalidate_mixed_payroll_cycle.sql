begin;

create table hr.payroll_report_aggregate_invalidations (
  id uuid primary key default gen_random_uuid(),
  aggregate_id uuid not null unique
    references hr.payroll_report_aggregates(id),
  evidence_artifact_id uuid not null references raw.raw_artifacts(id),
  reason_code text not null
    constraint payroll_report_invalidations_reason_allowed
    check (reason_code = 'mixed_payroll_cycle_header'),
  invalidator_version text not null
    constraint payroll_report_invalidations_version_present
    check (length(btrim(invalidator_version)) between 3 and 128),
  details jsonb not null default '{}'::jsonb
    constraint payroll_report_invalidations_details_object
    check (jsonb_typeof(details) = 'object'),
  invalidated_at timestamptz not null default statement_timestamp()
);

create index payroll_report_invalidations_evidence_idx
  on hr.payroll_report_aggregate_invalidations (evidence_artifact_id);

create function hr.verify_payroll_report_aggregate_invalidation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  aggregate_row hr.payroll_report_aggregates%rowtype;
  evidence_row raw.raw_artifacts%rowtype;
begin
  select * into aggregate_row
  from hr.payroll_report_aggregates
  where id = new.aggregate_id;

  select * into evidence_row
  from raw.raw_artifacts
  where id = new.evidence_artifact_id;

  if aggregate_row.id is null
    or evidence_row.id is null
    or aggregate_row.source_document_artifact_id <> evidence_row.id
    or evidence_row.artifact_kind <> 'document' then
    raise exception 'payroll invalidation requires its original document evidence'
      using errcode = '23514';
  end if;

  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_aggregate_invalidation()
  from public;

create trigger verify_payroll_report_aggregate_invalidation
before insert on hr.payroll_report_aggregate_invalidations
for each row execute function hr.verify_payroll_report_aggregate_invalidation();

create trigger reject_mutation
before update or delete on hr.payroll_report_aggregate_invalidations
for each row execute function audit.reject_mutation();

alter table hr.payroll_report_aggregate_invalidations enable row level security;
alter table hr.payroll_report_aggregate_invalidations force row level security;

revoke all on table hr.payroll_report_aggregate_invalidations
  from public, anon, authenticated, collector_worker;

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
  'mixed_payroll_cycle_header',
  'payroll-cycle-invalidation/1.0.0',
  jsonb_build_object(
    'observed_header', '1-Normal, 4-Adiant. 13º',
    'parser_version', aggregate.parser_version,
    'artifact_sha256', artifact.sha256
  ),
  statement_timestamp()
from hr.payroll_report_aggregates as aggregate
join raw.raw_artifacts as artifact
  on artifact.id = aggregate.source_document_artifact_id
where aggregate.reference_month = date '2025-01-01'
  and aggregate.payroll_cycle = 'thirteenth_advance'
  and aggregate.parser_version = 'payroll-report-aggregate/1.2.0'
  and artifact.sha256 =
    'd2345bdb7ccceb1553ba627758a70d74cd7124ef3af77dcc48237047e5190ac9'
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

comment on table hr.payroll_report_aggregate_invalidations is
  'Correções append-only que retiram um agregado comprovadamente inválido da projeção pública sem apagar a versão original.';
comment on column hr.payroll_report_aggregate_invalidations.reason_code is
  'Motivo determinístico da invalidação; não representa juízo reputacional.';
comment on function api.get_public_payroll_months(integer) is
  'Total mensal determinístico dos componentes vigentes e não invalidados da folha. Quantidade de vínculos vem somente da folha regular e cada PDF permanece citado.';

notify pgrst, 'reload schema';

commit;
