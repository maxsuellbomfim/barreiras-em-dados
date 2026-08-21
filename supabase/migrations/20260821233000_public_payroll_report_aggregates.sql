begin;

-- A relação oficial de servidores contém dados pessoais por linha. Esta tabela
-- recebe somente os totais mensais que passaram pela validação aritmética e
-- pela reconciliação com o total geral do próprio PDF.
create table hr.payroll_report_aggregates (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_document_artifact_id uuid not null references raw.raw_artifacts(id),
  public_body_id uuid not null references org.public_bodies(id),
  supersedes_id uuid,
  version integer not null default 1
    constraint payroll_report_aggregates_version_positive check (version > 0),
  report_kind text not null default 'municipal_staff'
    constraint payroll_report_aggregates_kind_allowed
    check (report_kind = 'municipal_staff'),
  reference_month date not null
    constraint payroll_report_aggregates_month_start
    check (reference_month = date_trunc('month', reference_month)::date),
  employee_count integer not null
    constraint payroll_report_aggregates_employee_count_nonnegative
    check (employee_count >= 0),
  gross_amount numeric(20,2) not null
    constraint payroll_report_aggregates_gross_nonnegative
    check (gross_amount >= 0),
  deduction_amount numeric(20,2) not null
    constraint payroll_report_aggregates_deduction_nonnegative
    check (deduction_amount >= 0),
  net_amount numeric(20,2) not null
    constraint payroll_report_aggregates_net_nonnegative
    check (net_amount >= 0),
  subtotal_count integer not null
    constraint payroll_report_aggregates_subtotals_positive
    check (subtotal_count > 0),
  currency char(3) not null default 'BRL'
    constraint payroll_report_aggregates_currency_brl check (currency = 'BRL'),
  validation_state text not null default 'validated'
    constraint payroll_report_aggregates_validation_state_allowed
    check (validation_state in ('validated', 'rejected')),
  parser_version text not null
    constraint payroll_report_aggregates_parser_version_present
    check (length(btrim(parser_version)) between 3 and 128),
  validated_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp(),
  constraint payroll_report_aggregates_arithmetic_exact
    check (gross_amount - deduction_amount = net_amount),
  constraint payroll_report_aggregates_identity_unique
    unique (id, public_body_id, report_kind, reference_month),
  constraint payroll_report_aggregates_supersedes_same_series
    foreign key (supersedes_id, public_body_id, report_kind, reference_month)
    references hr.payroll_report_aggregates (
      id, public_body_id, report_kind, reference_month
    ),
  constraint payroll_report_aggregates_version_chain check (
    (version = 1 and supersedes_id is null)
    or (version > 1 and supersedes_id is not null)
  ),
  constraint payroll_report_aggregates_source_parser_unique
    unique (source_document_artifact_id, parser_version)
);

create unique index payroll_report_aggregates_one_successor_idx
  on hr.payroll_report_aggregates (supersedes_id)
  where supersedes_id is not null;
create index payroll_report_aggregates_supersedes_series_idx
  on hr.payroll_report_aggregates (
    supersedes_id, public_body_id, report_kind, reference_month
  );
create index payroll_report_aggregates_public_query_idx
  on hr.payroll_report_aggregates (
    reference_month desc, public_body_id, report_kind, version desc
  ) where validation_state = 'validated';
create index payroll_report_aggregates_origin_idx
  on hr.payroll_report_aggregates (origin_raw_record_id);
create index payroll_report_aggregates_public_body_idx
  on hr.payroll_report_aggregates (public_body_id);

create function hr.verify_payroll_report_aggregate_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  origin_record raw.raw_records%rowtype;
  source_document raw.raw_artifacts%rowtype;
  source_year text;
  source_month text;
begin
  select * into origin_record
  from raw.raw_records
  where id = new.origin_raw_record_id;

  select * into source_document
  from raw.raw_artifacts
  where id = new.source_document_artifact_id;

  if origin_record.id is null
    or origin_record.record_type <> 'municipal_transparency_servidores'
    or origin_record.payload ->> 'tipo' <> '1' then
    raise exception 'payroll aggregate requires an official municipal staff catalog record'
      using errcode = '23514';
  end if;

  source_year := origin_record.payload ->> 'ano_ref';
  source_month := origin_record.payload ->> 'mes_ref';
  if source_year is null or source_year !~ '^[0-9]{4}$'
    or source_month is null or source_month !~ '^(?:[1-9]|1[0-2])$'
    or make_date(source_year::integer, source_month::integer, 1)
      <> new.reference_month then
    raise exception 'payroll aggregate reference month differs from official catalog'
      using errcode = '23514';
  end if;

  if source_document.id is null
    or source_document.artifact_kind <> 'document'
    or source_document.metadata ->> 'schema_name'
      <> 'municipal-transparency-document'
    or source_document.metadata ->> 'source_record_key'
      is distinct from origin_record.source_record_key
    or source_document.source_url
      is distinct from origin_record.payload ->> 'url' then
    raise exception 'payroll aggregate document does not match official catalog evidence'
      using errcode = '23514';
  end if;

  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_aggregate_lineage() from public;

create trigger verify_payroll_report_aggregate_lineage
before insert on hr.payroll_report_aggregates
for each row execute function hr.verify_payroll_report_aggregate_lineage();

create trigger reject_mutation
before update or delete on hr.payroll_report_aggregates
for each row execute function audit.reject_mutation();

alter table hr.payroll_report_aggregates enable row level security;
alter table hr.payroll_report_aggregates force row level security;

revoke all on table hr.payroll_report_aggregates
  from public, anon, authenticated;

grant usage on schema hr to collector_worker;
grant select, insert on table hr.payroll_report_aggregates to collector_worker;

create policy collector_worker_payroll_report_aggregates_select
on hr.payroll_report_aggregates
for select to collector_worker
using (true);

create policy collector_worker_payroll_report_aggregates_insert
on hr.payroll_report_aggregates
for insert to collector_worker
with check (true);

create function api.get_public_payroll_months(page_size integer default 24)
returns table (
  reference_month text,
  public_body_name text,
  employee_count integer,
  gross_amount numeric(20,2),
  deduction_amount numeric(20,2),
  net_amount numeric(20,2),
  subtotal_count integer,
  source_url text,
  artifact_sha256 text,
  source_retrieved_at timestamptz,
  parser_version text
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
  select
    to_char(aggregate.reference_month, 'YYYY-MM-DD'),
    body.name,
    aggregate.employee_count,
    aggregate.gross_amount,
    aggregate.deduction_amount,
    aggregate.net_amount,
    aggregate.subtotal_count,
    artifact.source_url,
    artifact.sha256,
    artifact.retrieved_at,
    aggregate.parser_version
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
  order by aggregate.reference_month desc, aggregate.id
  limit page_size;
end;
$function$;

revoke all on function api.get_public_payroll_months(integer) from public;
grant execute on function api.get_public_payroll_months(integer)
  to anon, authenticated;

comment on table hr.payroll_report_aggregates is
  'Totais mensais da folha validados contra subtotais do PDF oficial. Não contém linhas individuais nem identificadores pessoais.';
comment on function api.get_public_payroll_months(integer) is
  'Projeção pública somente de totais mensais validados da folha, com fonte e hash do PDF oficial.';

notify pgrst, 'reload schema';

commit;
