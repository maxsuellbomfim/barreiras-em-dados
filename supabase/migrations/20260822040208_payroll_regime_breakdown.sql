begin;

create table hr.payroll_report_regime_breakdowns (
  id uuid primary key default gen_random_uuid(),
  payroll_report_aggregate_id uuid not null unique
    references hr.payroll_report_aggregates(id),
  categories jsonb not null
    constraint payroll_report_regime_categories_array
    check (jsonb_typeof(categories) = 'array'),
  parser_version text not null
    constraint payroll_report_regime_parser_present
    check (length(btrim(parser_version)) between 3 and 128),
  validated_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp()
);

create index payroll_report_regime_aggregate_idx
  on hr.payroll_report_regime_breakdowns (payroll_report_aggregate_id);

create function hr.verify_payroll_report_regime_breakdown()
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
  item_deduction numeric(20,2);
  item_net numeric(20,2);
  total_count integer := 0;
  total_gross numeric(20,2) := 0;
  total_deduction numeric(20,2) := 0;
  total_net numeric(20,2) := 0;
begin
  select * into parent
  from hr.payroll_report_aggregates
  where id = new.payroll_report_aggregate_id;

  if parent.id is null or parent.validation_state <> 'validated' then
    raise exception 'regime breakdown requires a validated payroll aggregate'
      using errcode = '23514';
  end if;
  if new.parser_version <> 'payroll-regime-breakdown/1.0.0' then
    raise exception 'regime breakdown parser version is not publishable'
      using errcode = '23514';
  end if;
  if jsonb_array_length(new.categories) < 1
    or jsonb_array_length(new.categories) > 16 then
    raise exception 'categorias do vínculo devem conter entre 1 e 16 itens'
      using errcode = '23514';
  end if;

  for item in select value from jsonb_array_elements(new.categories)
  loop
    if jsonb_typeof(item) <> 'object'
      or not item ?& array[
        'regime_code', 'regime_label', 'employee_count', 'gross_amount',
        'deduction_amount', 'net_amount'
      ]
      or (select count(*) from jsonb_object_keys(item)) <> 6 then
      raise exception 'categorias do vínculo possuem campos inválidos'
        using errcode = '23514';
    end if;

    code := item ->> 'regime_code';
    label := item ->> 'regime_label';
    if code not in (
      'statutory', 'commissioned', 'selection_process', 'ceded',
      'political_agent', 'guardianship_council', 'pensioner',
      'temporary_worker'
    ) or label is distinct from (case code
      when 'statutory' then 'Estatutários'
      when 'commissioned' then 'Cargos em comissão'
      when 'selection_process' then 'Processo seletivo'
      when 'ceded' then 'Cedidos'
      when 'political_agent' then 'Agentes políticos'
      when 'guardianship_council' then 'Conselho tutelar'
      when 'pensioner' then 'Pensionistas'
      when 'temporary_worker' then 'Trabalhadores temporários'
    end) then
      raise exception 'regime/vínculo público desconhecido'
        using errcode = '23514';
    end if;
    if code = any(seen_codes) then
      raise exception 'regime/vínculo duplicado no agregado'
        using errcode = '23514';
    end if;
    seen_codes := array_append(seen_codes, code);

    if item ->> 'employee_count' !~ '^[0-9]+$'
      or item ->> 'gross_amount' !~ '^[0-9]+\.[0-9]{2}$'
      or item ->> 'deduction_amount' !~ '^[0-9]+\.[0-9]{2}$'
      or item ->> 'net_amount' !~ '^[0-9]+\.[0-9]{2}$' then
      raise exception 'categorias do vínculo possuem números inválidos'
        using errcode = '23514';
    end if;
    item_count := (item ->> 'employee_count')::integer;
    item_gross := (item ->> 'gross_amount')::numeric(20,2);
    item_deduction := (item ->> 'deduction_amount')::numeric(20,2);
    item_net := (item ->> 'net_amount')::numeric(20,2);
    if item_gross < 0 or item_deduction < 0 or item_net < 0
      or item_gross - item_deduction <> item_net then
      raise exception 'aritmética de regime/vínculo não fecha'
        using errcode = '23514';
    end if;
    total_count := total_count + item_count;
    total_gross := total_gross + item_gross;
    total_deduction := total_deduction + item_deduction;
    total_net := total_net + item_net;
  end loop;

  if total_count <> parent.employee_count
    or total_gross <> parent.gross_amount
    or total_deduction <> parent.deduction_amount
    or total_net <> parent.net_amount then
    raise exception 'soma das categorias do vínculo diverge do agregado da folha'
      using errcode = '23514';
  end if;
  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_regime_breakdown()
  from public;

create trigger verify_payroll_report_regime_breakdown
before insert on hr.payroll_report_regime_breakdowns
for each row execute function hr.verify_payroll_report_regime_breakdown();

create trigger reject_mutation
before update or delete on hr.payroll_report_regime_breakdowns
for each row execute function audit.reject_mutation();

alter table hr.payroll_report_regime_breakdowns enable row level security;
alter table hr.payroll_report_regime_breakdowns force row level security;

revoke all on table hr.payroll_report_regime_breakdowns
  from public, anon, authenticated;
grant select, insert on table hr.payroll_report_regime_breakdowns
  to collector_worker;

create policy collector_worker_payroll_regime_select
on hr.payroll_report_regime_breakdowns
for select to collector_worker
using (true);

create policy collector_worker_payroll_regime_insert
on hr.payroll_report_regime_breakdowns
for insert to collector_worker
with check (true);

create function hr.get_pending_payroll_regime_documents(
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
    raise exception 'limite de detalhamentos da folha inválido'
      using errcode = '22023';
  end if;
  if target_reference_month is not null and (
    target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month
      <> date_trunc('month', target_reference_month)::date
  ) then
    raise exception 'competência do detalhamento da folha inválida'
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
      from hr.payroll_report_regime_breakdowns as breakdown
      where breakdown.payroll_report_aggregate_id = aggregate.id
        and breakdown.parser_version = 'payroll-regime-breakdown/1.0.0'
    )
  order by aggregate.reference_month desc, aggregate.payroll_cycle,
    aggregate.id
  limit requested_limit;
end;
$function$;

revoke all on function hr.get_pending_payroll_regime_documents(integer, date)
  from public;
grant execute on function hr.get_pending_payroll_regime_documents(integer, date)
  to collector_worker;

create function api.get_public_payroll_regime_breakdown(
  target_reference_month date
)
returns table (
  reference_month text,
  regime_code text,
  regime_label text,
  employee_count integer,
  gross_amount numeric(20,2),
  deduction_amount numeric(20,2),
  net_amount numeric(20,2),
  source_document_count integer,
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
    raise exception 'competência do detalhamento da folha inválida'
      using errcode = '22023';
  end if;

  return query
  with current_components as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    where aggregate.reference_month = target_reference_month
      and aggregate.report_kind = 'municipal_staff'
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
  ), complete_components as (
    select component.*, breakdown.categories
    from current_components as component
    join hr.payroll_report_regime_breakdowns as breakdown
      on breakdown.payroll_report_aggregate_id = component.id
     and breakdown.parser_version = 'payroll-regime-breakdown/1.0.0'
    where (select count(*) from current_components)
      = (select count(*)
           from current_components as expected
           join hr.payroll_report_regime_breakdowns as available
             on available.payroll_report_aggregate_id = expected.id
            and available.parser_version = 'payroll-regime-breakdown/1.0.0')
      and (select count(*) from current_components) > 0
  ), expanded as (
    select
      component.reference_month,
      component.id as component_id,
      component.payroll_cycle,
      item ->> 'regime_code' as regime_code,
      item ->> 'regime_label' as regime_label,
      (item ->> 'employee_count')::integer as employee_count,
      (item ->> 'gross_amount')::numeric(20,2) as gross_amount,
      (item ->> 'deduction_amount')::numeric(20,2) as deduction_amount,
      (item ->> 'net_amount')::numeric(20,2) as net_amount
    from complete_components as component
    cross join lateral jsonb_array_elements(component.categories) as item
  )
  select
    to_char(expanded.reference_month, 'YYYY-MM-DD'),
    expanded.regime_code,
    max(expanded.regime_label),
    sum(
      case when expanded.payroll_cycle = 'regular'
        then expanded.employee_count else 0 end
    )::integer,
    sum(expanded.gross_amount)::numeric(20,2),
    sum(expanded.deduction_amount)::numeric(20,2),
    sum(expanded.net_amount)::numeric(20,2),
    (select count(*) from complete_components)::integer,
    'payroll-regime-monthly/1.0.0'::text
  from expanded
  group by expanded.reference_month, expanded.regime_code
  order by sum(expanded.gross_amount) desc, expanded.regime_code;
end;
$function$;

revoke all on function api.get_public_payroll_regime_breakdown(date)
  from public;
grant execute on function api.get_public_payroll_regime_breakdown(date)
  to anon, authenticated;

comment on table hr.payroll_report_regime_breakdowns is
  'Totais por regime/vínculo reconciliados com o agregado do PDF oficial. Não contém nomes, matrículas, cargos ou valores individuais.';
comment on function hr.get_pending_payroll_regime_documents(integer, date) is
  'Seleciona somente componentes validados pelo parser vigente e ainda sem detalhamento agregado por vínculo.';
comment on function api.get_public_payroll_regime_breakdown(date) is
  'Detalhamento mensal agregado por regime/vínculo, disponível somente quando todos os componentes oficiais do mês foram reconciliados.';

notify pgrst, 'reload schema';

commit;
