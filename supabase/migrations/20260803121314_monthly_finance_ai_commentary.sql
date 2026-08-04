begin;

-- Texto assistido por IA para o fechamento mensal. Os fatos são copiados do
-- fechamento determinístico e a resposta só fica pública após validação do
-- contrato sem números e sem conclusões reputacionais.
create table if not exists editorial.monthly_finance_commentaries (
  id uuid primary key default gen_random_uuid(),
  closure_id text not null,
  public_body_name text not null,
  fiscal_year smallint not null check (fiscal_year between 1900 and 2200),
  period_start date not null,
  period_end date not null,
  facts jsonb not null check (jsonb_typeof(facts) = 'object'),
  commentary text not null,
  statement_class text not null check (statement_class in ('fact', 'methodology')),
  provider text not null,
  model text not null,
  prompt_version text not null,
  validator_version text not null,
  raw_response jsonb not null check (jsonb_typeof(raw_response) in ('object', 'string')),
  version integer not null default 1 check (version > 0),
  status text not null default 'published'
    check (status in ('published', 'superseded', 'withdrawn')),
  published_at timestamptz not null default statement_timestamp(),
  supersedes_id uuid references editorial.monthly_finance_commentaries(id),
  created_at timestamptz not null default statement_timestamp(),
  unique (closure_id, version)
);

create index if not exists monthly_finance_commentaries_public_idx
  on editorial.monthly_finance_commentaries (closure_id, status, version desc);
create index if not exists monthly_finance_commentaries_supersedes_idx
  on editorial.monthly_finance_commentaries (supersedes_id);

alter table editorial.monthly_finance_commentaries enable row level security;
revoke all on table editorial.monthly_finance_commentaries from public, anon, authenticated;

drop policy if exists collector_worker_monthly_finance_commentaries_select
  on editorial.monthly_finance_commentaries;
create policy collector_worker_monthly_finance_commentaries_select
  on editorial.monthly_finance_commentaries
  for select to collector_worker using (true);

drop policy if exists collector_worker_monthly_finance_commentaries_insert
  on editorial.monthly_finance_commentaries;
create policy collector_worker_monthly_finance_commentaries_insert
  on editorial.monthly_finance_commentaries
  for insert to collector_worker with check (true);

grant usage on schema editorial to collector_worker;
grant select, insert on table editorial.monthly_finance_commentaries to collector_worker;

drop function if exists api.get_public_monthly_finance_commentaries(integer, smallint);
create function api.get_public_monthly_finance_commentaries(
  page_size integer default 24,
  fiscal_year_filter smallint default null
)
returns table (
  closure_id text,
  commentary text,
  statement_class text,
  prompt_version text,
  validator_version text,
  published_at timestamptz
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 120 then
    raise exception 'page_size deve estar entre 1 e 120'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  select
    current_commentary.closure_id,
    current_commentary.commentary,
    current_commentary.statement_class,
    current_commentary.prompt_version,
    current_commentary.validator_version,
    current_commentary.published_at
  from (
    select distinct on (commentary.closure_id)
      commentary.*
    from editorial.monthly_finance_commentaries as commentary
    where commentary.status = 'published'
      and (
        fiscal_year_filter is null
        or commentary.fiscal_year = fiscal_year_filter
      )
    order by commentary.closure_id, commentary.version desc,
      commentary.published_at desc, commentary.id desc
  ) as current_commentary
  order by current_commentary.period_start desc,
    current_commentary.public_body_name
  limit page_size;
end;
$function$;

revoke all on function api.get_public_monthly_finance_commentaries(integer, smallint)
  from public;
grant execute on function api.get_public_monthly_finance_commentaries(integer, smallint)
  to anon, authenticated, collector_worker;

comment on table editorial.monthly_finance_commentaries is
  'Explicações mensais assistidas por IA; valores e cobertura vêm do fechamento determinístico.';
comment on function api.get_public_monthly_finance_commentaries(integer, smallint) is
  'Explicações públicas validadas do fechamento mensal, sem acesso ao texto bruto da resposta.';

commit;
