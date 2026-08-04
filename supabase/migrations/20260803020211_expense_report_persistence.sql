-- Persistência versionada do Demonstrativo de Despesa Analítica.
-- As linhas são um retrato de execução orçamentária; não são empenhos
-- individuais e não devem ser somadas com pagamentos de outra fonte.

create table if not exists finance.expense_reports (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_document_artifact_id uuid not null references raw.raw_artifacts(id),
  public_body_id uuid not null references org.public_bodies(id),
  supersedes_id uuid references finance.expense_reports(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  fiscal_year smallint not null,
  period_start date not null,
  period_end date not null,
  total_fixed_amount numeric(20,2) not null,
  total_additions_amount numeric(20,2) not null,
  total_reductions_amount numeric(20,2) not null,
  total_updated_amount numeric(20,2) not null,
  total_committed_period_amount numeric(20,2) not null,
  total_committed_to_date_amount numeric(20,2) not null,
  total_liquidated_period_amount numeric(20,2) not null,
  total_liquidated_to_date_amount numeric(20,2) not null,
  total_paid_period_amount numeric(20,2) not null,
  total_paid_to_date_amount numeric(20,2) not null,
  total_unpaid_committed_amount numeric(20,2) not null,
  total_balance_amount numeric(20,2) not null,
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  methodology_version text not null default 'public-expense-pdf/1.0.0',
  validation_status text not null default 'needs_review' check (
    validation_status in (
      'extracted', 'validated', 'needs_source', 'needs_review', 'superseded'
    )
  ),
  published_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  check (period_start <= period_end),
  check (fiscal_year = extract(year from period_end)::smallint),
  check (validation_status <> 'validated' or published_at is not null)
);

create unique index if not exists expense_reports_source_version_idx
  on finance.expense_reports (source_document_artifact_id, version);

create unique index if not exists expense_reports_external_version_idx
  on finance.expense_reports (public_body_id, external_id, version)
  where external_id is not null;

create index if not exists expense_reports_period_idx
  on finance.expense_reports (public_body_id, period_end desc, validation_status);

create index if not exists expense_reports_origin_idx
  on finance.expense_reports (origin_raw_record_id);

create index if not exists expense_reports_document_idx
  on finance.expense_reports (source_document_artifact_id);

create index if not exists expense_reports_supersedes_idx
  on finance.expense_reports (supersedes_id);

create table if not exists finance.expense_lines (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references finance.expense_reports(id),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  line_number integer not null check (line_number > 0),
  expense_code text not null,
  description text not null,
  source_code text not null,
  fixed_amount numeric(20,2) not null,
  additions_amount numeric(20,2) not null,
  reductions_amount numeric(20,2) not null,
  updated_amount numeric(20,2) not null,
  committed_period_amount numeric(20,2) not null,
  committed_to_date_amount numeric(20,2) not null,
  liquidated_period_amount numeric(20,2) not null,
  liquidated_to_date_amount numeric(20,2) not null,
  paid_period_amount numeric(20,2) not null,
  paid_to_date_amount numeric(20,2) not null,
  unpaid_committed_amount numeric(20,2) not null,
  balance_amount numeric(20,2) not null,
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  methodology_version text not null default 'public-expense-pdf/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  unique (report_id, line_number)
);

create index if not exists expense_lines_report_code_idx
  on finance.expense_lines (report_id, expense_code);

create index if not exists expense_lines_origin_idx
  on finance.expense_lines (origin_raw_record_id);

create index if not exists expense_lines_period_amount_idx
  on finance.expense_lines (report_id, paid_period_amount desc);

grant usage on schema finance to collector_worker;
grant select, insert on finance.expense_reports to collector_worker;
grant select, insert on finance.expense_lines to collector_worker;

create policy collector_worker_expense_reports_select
  on finance.expense_reports
  for select to collector_worker
  using (true);

create policy collector_worker_expense_reports_insert
  on finance.expense_reports
  for insert to collector_worker
  with check (true);

create policy collector_worker_expense_lines_select
  on finance.expense_lines
  for select to collector_worker
  using (true);

create policy collector_worker_expense_lines_insert
  on finance.expense_lines
  for insert to collector_worker
  with check (true);

drop function if exists api.get_public_expense_reports(integer, smallint);

create function api.get_public_expense_reports(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  expense_report_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  total_updated_amount numeric,
  total_committed_period_amount numeric,
  total_committed_to_date_amount numeric,
  total_liquidated_period_amount numeric,
  total_liquidated_to_date_amount numeric,
  total_paid_period_amount numeric,
  total_paid_to_date_amount numeric,
  total_unpaid_committed_amount numeric,
  total_balance_amount numeric,
  currency text,
  public_body_name text,
  source_url text,
  document_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text,
  validation_status text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with ranked as (
    select
      report.*,
      row_number() over (
        partition by report.source_document_artifact_id
        order by report.version desc, report.created_at desc, report.id desc
      ) as current_row
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
  )
  select
    report.id,
    report.fiscal_year,
    report.period_start,
    report.period_end,
    report.total_updated_amount,
    report.total_committed_period_amount,
    report.total_committed_to_date_amount,
    report.total_liquidated_period_amount,
    report.total_liquidated_to_date_amount,
    report.total_paid_period_amount,
    report.total_paid_to_date_amount,
    report.total_unpaid_committed_amount,
    report.total_balance_amount,
    report.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    'public-expense-reports/1.0.0',
    report.validation_status
  from ranked as report
  join org.public_bodies as body
    on body.id = report.public_body_id
  join raw.raw_records as origin
    on origin.id = report.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = report.source_document_artifact_id
   and document.artifact_kind = 'document'
  where report.current_row = 1
  order by report.period_end desc, report.created_at desc, report.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_expense_reports(integer, smallint) from public;
grant execute on function api.get_public_expense_reports(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_expense_reports(integer, smallint) is
  'Relatorios de despesa validados com periodo, empenho, liquidacao, pagamento e evidencia preservada.';
