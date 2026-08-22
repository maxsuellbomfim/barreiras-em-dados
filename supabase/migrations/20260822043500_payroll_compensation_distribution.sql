begin;

create table hr.payroll_report_compensation_distributions (
  id uuid primary key default gen_random_uuid(),
  payroll_report_aggregate_id uuid not null unique
    references hr.payroll_report_aggregates(id),
  bands jsonb not null
    constraint payroll_compensation_bands_array
    check (jsonb_typeof(bands) = 'array'),
  maximum_gross_amount numeric(20,2) not null
    constraint payroll_compensation_maximum_nonnegative
    check (maximum_gross_amount >= 0),
  parser_version text not null
    constraint payroll_compensation_parser_present
    check (length(btrim(parser_version)) between 3 and 128),
  validated_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp()
);

create function hr.verify_payroll_report_compensation_distribution()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  parent hr.payroll_report_aggregates%rowtype;
  item jsonb;
  code text;
  label text;
  seen_codes text[] := array[]::text[];
  item_count integer;
  item_gross numeric(20,2);
  total_count integer := 0;
  total_gross numeric(20,2) := 0;
begin
  select * into parent
  from hr.payroll_report_aggregates
  where id = new.payroll_report_aggregate_id;

  if parent.id is null
    or parent.validation_state <> 'validated'
    or parent.report_kind <> 'municipal_staff'
    or parent.payroll_cycle <> 'regular' then
    raise exception 'compensation distribution requires a validated regular payroll'
      using errcode = '23514';
  end if;
  if new.parser_version <> 'payroll-compensation-bands/1.0.0' then
    raise exception 'compensation distribution parser version is not publishable'
      using errcode = '23514';
  end if;
  if jsonb_array_length(new.bands) < 1
    or jsonb_array_length(new.bands) > 6 then
    raise exception 'faixas de provento devem conter entre 1 e 6 itens'
      using errcode = '23514';
  end if;

  for item in select value from jsonb_array_elements(new.bands)
  loop
    if jsonb_typeof(item) <> 'object'
      or not item ?& array[
        'band_code', 'band_label', 'employee_count', 'gross_amount'
      ]
      or (select count(*) from jsonb_object_keys(item)) <> 4 then
      raise exception 'faixas de provento possuem campos inválidos'
        using errcode = '23514';
    end if;

    code := item ->> 'band_code';
    label := item ->> 'band_label';
    if code not in (
      'up_to_1500', 'from_1500_01_to_3000',
      'from_3000_01_to_5000', 'from_5000_01_to_10000',
      'from_10000_01_to_20000', 'above_20000'
    ) or label is distinct from (case code
      when 'up_to_1500' then 'Até R$ 1.500'
      when 'from_1500_01_to_3000' then 'De R$ 1.500,01 a R$ 3 mil'
      when 'from_3000_01_to_5000' then 'De R$ 3.000,01 a R$ 5 mil'
      when 'from_5000_01_to_10000' then 'De R$ 5.000,01 a R$ 10 mil'
      when 'from_10000_01_to_20000' then 'De R$ 10.000,01 a R$ 20 mil'
      when 'above_20000' then 'Acima de R$ 20 mil'
    end) then
      raise exception 'faixa pública de provento desconhecida'
        using errcode = '23514';
    end if;
    if code = any(seen_codes) then
      raise exception 'faixa de provento duplicada no agregado'
        using errcode = '23514';
    end if;
    seen_codes := array_append(seen_codes, code);

    if item ->> 'employee_count' !~ '^[1-9][0-9]*$'
      or item ->> 'gross_amount' !~ '^[0-9]+\.[0-9]{2}$' then
      raise exception 'faixas de provento possuem números inválidos'
        using errcode = '23514';
    end if;
    item_count := (item ->> 'employee_count')::integer;
    item_gross := (item ->> 'gross_amount')::numeric(20,2);
    if item_gross < 0 then
      raise exception 'total bruto da faixa deve ser não negativo'
        using errcode = '23514';
    end if;
    total_count := total_count + item_count;
    total_gross := total_gross + item_gross;
  end loop;

  if total_count <> parent.employee_count
    or total_gross <> parent.gross_amount then
    raise exception 'soma das faixas diverge do agregado da folha regular'
      using errcode = '23514';
  end if;
  if new.maximum_gross_amount > parent.gross_amount
    or new.maximum_gross_amount < round(parent.gross_amount / parent.employee_count, 2)
  then
    raise exception 'maior provento bruto incompatível com o agregado'
      using errcode = '23514';
  end if;
  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_compensation_distribution()
  from public;

create trigger verify_payroll_report_compensation_distribution
before insert on hr.payroll_report_compensation_distributions
for each row execute function hr.verify_payroll_report_compensation_distribution();

create trigger reject_mutation
before update or delete on hr.payroll_report_compensation_distributions
for each row execute function audit.reject_mutation();

alter table hr.payroll_report_compensation_distributions enable row level security;
alter table hr.payroll_report_compensation_distributions force row level security;

revoke all on table hr.payroll_report_compensation_distributions
  from public, anon, authenticated;
grant select, insert on table hr.payroll_report_compensation_distributions
  to collector_worker;

create policy collector_worker_payroll_compensation_select
on hr.payroll_report_compensation_distributions
for select to collector_worker
using (true);

create policy collector_worker_payroll_compensation_insert
on hr.payroll_report_compensation_distributions
for insert to collector_worker
with check (true);

create function hr.get_pending_payroll_compensation_documents(
  requested_limit integer,
  target_reference_month date default null
)
returns table (
  aggregate_id text,
  artifact_id text,
  sha256 text,
  object_key text,
  byte_size bigint,
  parent_record_id text,
  source_url text,
  reference_month date
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if requested_limit is null or requested_limit < 1 or requested_limit > 20 then
    raise exception 'limite de distribuições da folha inválido'
      using errcode = '22023';
  end if;
  if target_reference_month is not null and (
    target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date
  ) then
    raise exception 'competência da distribuição da folha inválida'
      using errcode = '22023';
  end if;

  return query
  select
    aggregate.id::text,
    artifact.id::text,
    artifact.sha256,
    artifact.object_key,
    artifact.byte_size,
    aggregate.origin_raw_record_id::text,
    artifact.source_url,
    aggregate.reference_month
  from hr.payroll_report_aggregates as aggregate
  join raw.raw_artifacts as artifact
    on artifact.id = aggregate.source_document_artifact_id
  where aggregate.report_kind = 'municipal_staff'
    and aggregate.payroll_cycle = 'regular'
    and aggregate.validation_state = 'validated'
    and aggregate.parser_version = 'payroll-report-aggregate/1.4.0'
    and aggregate.reference_month = coalesce(
      target_reference_month,
      aggregate.reference_month
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregates as successor
      where successor.supersedes_id = aggregate.id
        and successor.validation_state <> 'rejected'
    )
    and not exists (
      select 1
      from hr.payroll_report_aggregate_invalidations as invalidation
      where invalidation.aggregate_id = aggregate.id
    )
    and not exists (
      select 1
      from hr.payroll_report_compensation_distributions as distribution
      where distribution.payroll_report_aggregate_id = aggregate.id
        and distribution.parser_version = 'payroll-compensation-bands/1.0.0'
    )
  order by aggregate.reference_month desc, aggregate.id
  limit requested_limit;
end;
$function$;

revoke all on function hr.get_pending_payroll_compensation_documents(integer, date)
  from public;
grant execute on function hr.get_pending_payroll_compensation_documents(integer, date)
  to collector_worker;

create function api.get_public_payroll_compensation_distribution(
  target_reference_month date
)
returns table (
  reference_month text,
  band_code text,
  band_label text,
  employee_count integer,
  gross_amount numeric(20,2),
  average_gross_amount numeric(20,2),
  maximum_gross_amount numeric(20,2),
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if target_reference_month is null
    or target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date then
    raise exception 'competência da distribuição da folha inválida'
      using errcode = '22023';
  end if;

  return query
  with current_regular as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    where aggregate.reference_month = target_reference_month
      and aggregate.report_kind = 'municipal_staff'
      and aggregate.payroll_cycle = 'regular'
      and aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
  ), available as (
    select aggregate.*, distribution.bands,
      distribution.maximum_gross_amount
    from current_regular as aggregate
    join hr.payroll_report_compensation_distributions as distribution
      on distribution.payroll_report_aggregate_id = aggregate.id
     and distribution.parser_version = 'payroll-compensation-bands/1.0.0'
    where (select count(*) from current_regular) = 1
  )
  select
    to_char(available.reference_month, 'YYYY-MM-DD'),
    item ->> 'band_code',
    item ->> 'band_label',
    (item ->> 'employee_count')::integer,
    (item ->> 'gross_amount')::numeric(20,2),
    round(available.gross_amount / available.employee_count, 2)::numeric(20,2),
    available.maximum_gross_amount,
    'payroll-compensation-monthly/1.0.0'::text
  from available
  cross join lateral jsonb_array_elements(available.bands) as item
  order by case item ->> 'band_code'
    when 'up_to_1500' then 1
    when 'from_1500_01_to_3000' then 2
    when 'from_3000_01_to_5000' then 3
    when 'from_5000_01_to_10000' then 4
    when 'from_10000_01_to_20000' then 5
    when 'above_20000' then 6
  end;
end;
$function$;

revoke all on function api.get_public_payroll_compensation_distribution(date)
  from public;
grant execute on function api.get_public_payroll_compensation_distribution(date)
  to anon, authenticated, collector_worker;

comment on table hr.payroll_report_compensation_distributions is
  'Faixas agregadas do provento bruto da folha regular. Não contém nomes, matrículas, cargos, CPF ou descontos individuais.';
comment on function hr.get_pending_payroll_compensation_documents(integer, date) is
  'Seleciona somente a folha regular vigente e validada ainda sem faixas agregadas.';
comment on function api.get_public_payroll_compensation_distribution(date) is
  'Distribuição pública mínima do provento bruto da folha regular, reconciliada com o total oficial e sem dados pessoais.';

notify pgrst, 'reload schema';

commit;
