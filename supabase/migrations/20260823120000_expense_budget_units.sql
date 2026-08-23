begin;

create table finance.expense_line_budget_units (
  id uuid primary key default gen_random_uuid(),
  expense_line_id uuid not null references finance.expense_lines(id),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_document_artifact_id uuid not null references raw.raw_artifacts(id),
  supersedes_id uuid references finance.expense_line_budget_units(id),
  version integer not null default 1 check (version > 0),
  budget_unit_code text not null check (budget_unit_code ~ '^[0-9]{6,8}$'),
  budget_unit_name text not null check (length(btrim(budget_unit_name)) > 0),
  methodology_version text not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (expense_line_id, version)
);

create index expense_line_budget_units_line_idx
  on finance.expense_line_budget_units (
    expense_line_id, version desc, created_at desc, id desc
  );

create index expense_line_budget_units_document_idx
  on finance.expense_line_budget_units (source_document_artifact_id);

create index expense_line_budget_units_origin_idx
  on finance.expense_line_budget_units (origin_raw_record_id);

create index expense_line_budget_units_supersedes_idx
  on finance.expense_line_budget_units (supersedes_id);

create function finance.validate_expense_budget_unit_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if not exists (
    select 1
    from finance.expense_lines as line
    join finance.expense_reports as report on report.id = line.report_id
    where line.id = new.expense_line_id
      and line.origin_raw_record_id = new.origin_raw_record_id
      and report.origin_raw_record_id = new.origin_raw_record_id
      and report.source_document_artifact_id
        = new.source_document_artifact_id
  ) then
    raise exception 'linhagem da unidade orcamentaria diverge da linha de despesa'
      using errcode = '23514';
  end if;
  return new;
end;
$function$;

revoke all on function finance.validate_expense_budget_unit_lineage()
  from public, anon, authenticated, collector_worker;

create trigger expense_line_budget_units_validate_lineage
before insert or update on finance.expense_line_budget_units
for each row execute function finance.validate_expense_budget_unit_lineage();

alter table finance.expense_line_budget_units enable row level security;
alter table finance.expense_line_budget_units force row level security;

grant select, insert on finance.expense_line_budget_units to collector_worker;

create policy collector_worker_expense_line_budget_units_select
  on finance.expense_line_budget_units
  for select to collector_worker
  using (true);

create policy collector_worker_expense_line_budget_units_insert
  on finance.expense_line_budget_units
  for insert to collector_worker
  with check (true);

create function api.get_public_expense_budget_unit_summary(
  report_filter uuid
)
returns table (
  expense_report_id uuid,
  budget_unit_code text,
  budget_unit_name text,
  budget_unit_name_count integer,
  line_count integer,
  report_line_count integer,
  allocated_line_count integer,
  committed_period_amount numeric,
  liquidated_period_amount numeric,
  paid_period_amount numeric,
  report_total_paid_amount numeric,
  allocated_total_paid_amount numeric,
  reconciliation_status text,
  paid_share_percent numeric,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if report_filter is null then
    raise exception 'report_filter e obrigatorio'
      using errcode = '22004';
  end if;

  return query
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  eligible_report as materialized (
    select report.*
    from (
      select
        candidate.*,
        row_number() over (
          partition by candidate.source_document_artifact_id
          order by candidate.version desc, candidate.created_at desc,
            candidate.id desc
        ) as current_row
      from finance.expense_reports as candidate
      join exact_lineage as lineage
        on lineage.origin_raw_record_id = candidate.origin_raw_record_id
       and lineage.document_artifact_id = candidate.source_document_artifact_id
      where candidate.validation_status = 'validated'
        and candidate.published_at is not null
        and candidate.id = report_filter
    ) as report
    where report.current_row = 1
  ),
  report_lines as materialized (
    select line.*
    from finance.expense_lines as line
    join eligible_report as report on report.id = line.report_id
    where line.origin_raw_record_id = report.origin_raw_record_id
  ),
  latest_allocations as materialized (
    select allocation.*
    from (
      select
        candidate.*,
        row_number() over (
          partition by candidate.expense_line_id
          order by candidate.version desc, candidate.created_at desc,
            candidate.id desc
        ) as current_row
      from finance.expense_line_budget_units as candidate
      join report_lines as line on line.id = candidate.expense_line_id
      join eligible_report as report
        on report.source_document_artifact_id
          = candidate.source_document_artifact_id
       and report.origin_raw_record_id = candidate.origin_raw_record_id
    ) as allocation
    where allocation.current_row = 1
  ),
  coverage as materialized (
    select
      report.id as expense_report_id,
      report.total_paid_period_amount as report_total_paid_amount,
      count(line.id)::integer as report_line_count,
      count(allocation.id)::integer as allocated_line_count
    from eligible_report as report
    left join report_lines as line on true
    left join latest_allocations as allocation
      on allocation.expense_line_id = line.id
    group by report.id, report.total_paid_period_amount
  ),
  grouped as materialized (
    select
      line.report_id as expense_report_id,
      allocation.budget_unit_code,
      min(btrim(allocation.budget_unit_name)) as budget_unit_name,
      count(distinct btrim(allocation.budget_unit_name))::integer
        as budget_unit_name_count,
      count(*)::integer as line_count,
      coalesce(sum(line.committed_period_amount), 0::numeric)
        as committed_period_amount,
      coalesce(sum(line.liquidated_period_amount), 0::numeric)
        as liquidated_period_amount,
      coalesce(sum(line.paid_period_amount), 0::numeric)
        as paid_period_amount
    from report_lines as line
    join latest_allocations as allocation
      on allocation.expense_line_id = line.id
    group by line.report_id, allocation.budget_unit_code
  ),
  reconciled as materialized (
    select
      grouped.*,
      coverage.report_line_count,
      coverage.allocated_line_count,
      coverage.report_total_paid_amount,
      sum(grouped.paid_period_amount) over (
        partition by grouped.expense_report_id
      ) as allocated_total_paid_amount
    from grouped
    join coverage using (expense_report_id)
  )
  select
    reconciled.expense_report_id,
    reconciled.budget_unit_code,
    reconciled.budget_unit_name,
    reconciled.budget_unit_name_count,
    reconciled.line_count,
    reconciled.report_line_count,
    reconciled.allocated_line_count,
    reconciled.committed_period_amount,
    reconciled.liquidated_period_amount,
    reconciled.paid_period_amount,
    reconciled.report_total_paid_amount,
    reconciled.allocated_total_paid_amount,
    case
      when reconciled.budget_unit_name_count <> 1 then 'source_conflict'
      when reconciled.allocated_line_count <> reconciled.report_line_count
        then 'partial'
      when reconciled.allocated_total_paid_amount
        <> reconciled.report_total_paid_amount then 'amount_mismatch'
      else 'matched'
    end,
    case
      when reconciled.budget_unit_name_count = 1
       and reconciled.allocated_line_count = reconciled.report_line_count
       and reconciled.allocated_total_paid_amount
         = reconciled.report_total_paid_amount
       and reconciled.report_total_paid_amount <> 0::numeric
        then round(
          reconciled.paid_period_amount * 100::numeric
          / reconciled.report_total_paid_amount,
          2
        )
      else null::numeric
    end,
    'public-expense-budget-unit-summary/1.0.0'
  from reconciled
  order by reconciled.paid_period_amount desc,
    reconciled.budget_unit_code asc;
end;
$function$;

revoke all on table finance.expense_line_budget_units from public;
revoke all on function api.get_public_expense_budget_unit_summary(uuid)
  from public;
grant execute on function api.get_public_expense_budget_unit_summary(uuid)
  to anon, authenticated;

comment on table finance.expense_line_budget_units is
  'Atribuicao versionada e literal da unidade orcamentaria que precede cada linha no demonstrativo oficial de despesa.';

comment on function api.get_public_expense_budget_unit_summary(uuid) is
  'Pagamentos por unidade orcamentaria; percentuais somente quando linhas, nomes e total do relatorio reconciliam integralmente.';

notify pgrst, 'reload schema';

commit;
