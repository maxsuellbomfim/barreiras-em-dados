-- Obrigações municipais normalizadas, sempre ligadas ao registro bruto.
-- Esta estrutura não calcula nem publica uma "dívida total": ela preserva
-- linhas reportadas por período para reconciliação entre fontes e versões.

create table finance.public_obligations (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  supersedes_id uuid,
  version integer not null default 1
    constraint public_obligations_version_positive check (version > 0),
  obligation_key text not null
    constraint public_obligations_key_format check (
    obligation_key ~ '^[a-z0-9][a-z0-9:_-]{2,255}$'
  ),
  obligation_type text not null
    constraint public_obligations_type_allowed check (
    obligation_type in (
      'loan',
      'precatorio',
      'accounts_payable',
      'restos_a_pagar_processados',
      'restos_a_pagar_nao_processados',
      'social_security',
      'court_order',
      'other'
    )
  ),
  description text not null
    constraint public_obligations_description_present
    check (length(btrim(description)) > 0),
  fiscal_year smallint not null
    constraint public_obligations_fiscal_year_range
    check (fiscal_year between 1988 and 9999),
  period_start date,
  period_end date not null,
  opening_balance numeric(20,2)
    constraint public_obligations_opening_balance_check check (
    opening_balance is null or opening_balance >= 0
  ),
  additions_amount numeric(20,2)
    constraint public_obligations_additions_amount_check check (
    additions_amount is null or additions_amount >= 0
  ),
  reductions_amount numeric(20,2)
    constraint public_obligations_reductions_amount_check check (
    reductions_amount is null or reductions_amount >= 0
  ),
  payments_amount numeric(20,2)
    constraint public_obligations_payments_amount_check check (
    payments_amount is null or payments_amount >= 0
  ),
  closing_balance numeric(20,2)
    constraint public_obligations_closing_balance_check check (
    closing_balance is null or closing_balance >= 0
  ),
  currency char(3) not null default 'BRL'
    constraint public_obligations_currency_brl check (currency = 'BRL'),
  status text not null
    constraint public_obligations_status_allowed check (
    status in ('reported', 'active', 'settled', 'suspended', 'disputed', 'unknown')
  ),
  validation_state text not null default 'extracted'
    constraint public_obligations_validation_state_allowed check (
    validation_state in (
      'extracted', 'validated', 'reconciled', 'conflict', 'rejected', 'superseded'
    )
  ),
  methodology_version text not null
    constraint public_obligations_methodology_present
    check (length(btrim(methodology_version)) > 0),
  validated_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  constraint public_obligations_identity_body_unique
    unique (id, public_body_id),
  constraint public_obligations_supersedes_same_body
    foreign key (supersedes_id, public_body_id)
    references finance.public_obligations (id, public_body_id),
  constraint public_obligations_key_version_unique
    unique (public_body_id, obligation_key, version),
  constraint public_obligations_period_order
    check (period_start is null or period_end >= period_start),
  constraint public_obligations_has_numeric_value check (
    num_nonnulls(
      opening_balance,
      additions_amount,
      reductions_amount,
      payments_amount,
      closing_balance
    ) >= 1
  ),
  constraint public_obligations_version_chain check (
    (version = 1 and supersedes_id is null)
    or (version > 1 and supersedes_id is not null)
  ),
  constraint public_obligations_validation_timestamp check (
    (validation_state in ('validated', 'reconciled') and validated_at is not null)
    or (validation_state not in ('validated', 'reconciled') and validated_at is null)
  ),
  constraint public_obligations_reconciled_has_closing_balance
    check (validation_state <> 'reconciled' or closing_balance is not null)
);

create index public_obligations_origin_raw_record_idx
  on finance.public_obligations (origin_raw_record_id);
create index public_obligations_public_body_idx
  on finance.public_obligations (public_body_id);
create unique index public_obligations_one_successor_idx
  on finance.public_obligations (supersedes_id, public_body_id);
create index public_obligations_public_query_idx
  on finance.public_obligations (
    fiscal_year desc,
    obligation_type,
    period_end desc
  )
  where validation_state in ('validated', 'reconciled');

create trigger reject_mutation
before update or delete on finance.public_obligations
for each row execute function audit.reject_mutation();

alter table finance.public_obligations enable row level security;
alter table finance.public_obligations force row level security;

revoke all on table finance.public_obligations
  from public, anon, authenticated;

grant usage on schema finance to collector_worker;
grant select, insert on table finance.public_obligations to collector_worker;

create policy collector_worker_public_obligations_select
on finance.public_obligations
for select to collector_worker
using (true);

create policy collector_worker_public_obligations_insert
on finance.public_obligations
for insert to collector_worker
with check (true);

create or replace function api.get_public_obligations(
  page_size integer default 100,
  fiscal_year_filter integer default null,
  obligation_type_filter text default null
)
returns table (
  obligation_id uuid,
  obligation_type text,
  description text,
  fiscal_year smallint,
  period_start text,
  period_end text,
  opening_balance numeric(20,2),
  additions_amount numeric(20,2),
  reductions_amount numeric(20,2),
  payments_amount numeric(20,2),
  closing_balance numeric(20,2),
  status text,
  validation_state text,
  source_url text,
  artifact_sha256 text,
  source_retrieved_at timestamptz,
  methodology_version text
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

  if obligation_type_filter is not null and obligation_type_filter not in (
    'loan',
    'precatorio',
    'accounts_payable',
    'restos_a_pagar_processados',
    'restos_a_pagar_nao_processados',
    'social_security',
    'court_order',
    'other'
  ) then
    raise exception 'obligation_type_filter nao permitido'
      using errcode = '22023';
  end if;

  return query
  select
    obligation.id,
    obligation.obligation_type,
    obligation.description,
    obligation.fiscal_year,
    to_char(obligation.period_start, 'YYYY-MM-DD'),
    to_char(obligation.period_end, 'YYYY-MM-DD'),
    obligation.opening_balance,
    obligation.additions_amount,
    obligation.reductions_amount,
    obligation.payments_amount,
    obligation.closing_balance,
    obligation.status,
    obligation.validation_state,
    artifact.source_url,
    artifact.sha256,
    artifact.retrieved_at,
    obligation.methodology_version
  from finance.public_obligations as obligation
  join raw.raw_records as origin
    on origin.id = obligation.origin_raw_record_id
  join raw.raw_artifacts as artifact
    on artifact.id = origin.raw_artifact_id
  where obligation.validation_state in ('validated', 'reconciled')
    and (
      fiscal_year_filter is null
      or obligation.fiscal_year = fiscal_year_filter
    )
    and (
      obligation_type_filter is null
      or obligation.obligation_type = obligation_type_filter
    )
    and not exists (
      select 1
      from finance.public_obligations as successor
      where successor.supersedes_id = obligation.id
        and successor.validation_state <> 'rejected'
    )
  order by
    obligation.period_end desc,
    obligation.fiscal_year desc,
    obligation.obligation_type,
    obligation.id
  limit page_size;
end;
$function$;

revoke all on function api.get_public_obligations(integer, integer, text)
  from public;
grant execute on function api.get_public_obligations(integer, integer, text)
  to anon, authenticated;

comment on table finance.public_obligations is
  'Obrigações reportadas por período, versionadas e ligadas à evidência bruta. Não representa dívida total consolidada.';
comment on function api.get_public_obligations(integer, integer, text) is
  'Projeção de obrigações validadas ou reconciliadas; não soma dívida municipal.';
