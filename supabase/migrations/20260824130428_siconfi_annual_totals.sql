begin;

create table finance.siconfi_annual_totals (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_artifact_id uuid not null references raw.raw_artifacts(id),
  public_body_id uuid not null references org.public_bodies(id),
  supersedes_id uuid references finance.siconfi_annual_totals(id),
  version integer not null default 1 check (version > 0),
  fiscal_year smallint not null check (fiscal_year between 1988 and 9999),
  metric_key text not null check (
    metric_key in (
      'gross_revenue_realized',
      'fundeb_deductions',
      'expense_committed',
      'expense_liquidated',
      'expense_paid',
      'nonprocessed_payables_registered',
      'processed_payables_registered'
    )
  ),
  amount numeric(20,2) not null,
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  official_annex text not null,
  official_label text not null,
  official_column_label text not null,
  official_account_code text not null,
  official_account_label text not null,
  validation_status text not null default 'validated' check (
    validation_status in ('validated', 'conflict', 'superseded')
  ),
  methodology_version text not null check (length(btrim(methodology_version)) > 0),
  created_at timestamptz not null default statement_timestamp(),
  unique (origin_raw_record_id),
  unique (fiscal_year, metric_key, version),
  check (
    (version = 1 and supersedes_id is null)
    or (version > 1 and supersedes_id is not null)
  )
);

create unique index siconfi_annual_totals_one_successor_idx
  on finance.siconfi_annual_totals (supersedes_id)
  where supersedes_id is not null;

create index siconfi_annual_totals_supersedes_idx
  on finance.siconfi_annual_totals (supersedes_id);

create index siconfi_annual_totals_public_body_idx
  on finance.siconfi_annual_totals (public_body_id);

create index siconfi_annual_totals_public_idx
  on finance.siconfi_annual_totals (
    fiscal_year desc, metric_key, version desc
  )
  where validation_status = 'validated';

create index siconfi_annual_totals_artifact_idx
  on finance.siconfi_annual_totals (source_artifact_id);

create function finance.validate_siconfi_annual_total_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  origin record;
  predecessor record;
begin
  select
    raw_record.raw_artifact_id,
    raw_record.record_type,
    raw_record.payload,
    artifact.source_url,
    body.ibge_code
  into origin
  from raw.raw_records as raw_record
  join raw.raw_artifacts as artifact on artifact.id = raw_record.raw_artifact_id
  join org.public_bodies as body on body.id = new.public_body_id
  where raw_record.id = new.origin_raw_record_id;

  if origin is null
     or origin.record_type <> 'siconfi_dca_line'
     or origin.raw_artifact_id <> new.source_artifact_id
     or origin.ibge_code <> '2903201'
     or origin.payload ->> 'cod_ibge' <> '2903201'
     or origin.payload ->> 'instituicao'
       <> 'Prefeitura Municipal de Barreiras - BA'
     or origin.source_url not like
       'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca%'
     or origin.payload ->> 'exercicio' <> new.fiscal_year::text
     or origin.payload ->> 'anexo' <> new.official_annex
     or origin.payload ->> 'rotulo' <> new.official_label
     or origin.payload ->> 'coluna' <> new.official_column_label
     or origin.payload ->> 'cod_conta' <> new.official_account_code
     or origin.payload ->> 'conta' <> new.official_account_label
     or origin.payload ->> 'valor' is null
     or (origin.payload ->> 'valor')::numeric <> new.amount then
    raise exception 'linhagem SICONFI diverge do registro bruto'
      using errcode = '23514';
  end if;

  if new.supersedes_id is not null then
    select fiscal_year, metric_key, version
    into predecessor
    from finance.siconfi_annual_totals
    where id = new.supersedes_id;

    if predecessor is null
       or predecessor.fiscal_year <> new.fiscal_year
       or predecessor.metric_key <> new.metric_key
       or predecessor.version + 1 <> new.version then
      raise exception 'cadeia de versão SICONFI inválida'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$function$;

create trigger validate_siconfi_annual_total_lineage
before insert on finance.siconfi_annual_totals
for each row execute function finance.validate_siconfi_annual_total_lineage();

create trigger reject_mutation
before update or delete on finance.siconfi_annual_totals
for each row execute function audit.reject_mutation();

alter table finance.siconfi_annual_totals enable row level security;
alter table finance.siconfi_annual_totals force row level security;

revoke all on table finance.siconfi_annual_totals
  from public, anon, authenticated;

grant usage on schema finance to collector_worker;
grant select, insert on table finance.siconfi_annual_totals to collector_worker;

create policy collector_worker_siconfi_annual_totals_select
on finance.siconfi_annual_totals
for select to collector_worker
using (true);

create policy collector_worker_siconfi_annual_totals_insert
on finance.siconfi_annual_totals
for insert to collector_worker
with check (true);

create or replace function api.get_public_siconfi_annual_totals(
  page_size integer default 70,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  total_id uuid,
  fiscal_year smallint,
  metric_key text,
  amount numeric(20,2),
  currency text,
  official_annex text,
  official_label text,
  official_column_label text,
  official_account_code text,
  official_account_label text,
  source_url text,
  source_artifact_sha256 text,
  source_retrieved_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if page_size < 1 or page_size > 140 then
    raise exception 'page_size deve estar entre 1 e 140'
      using errcode = '22023';
  end if;

  if fiscal_year_from < 1988
     or fiscal_year_from > effective_year_to
     or effective_year_to > 2200 then
    raise exception 'intervalo fiscal inválido'
      using errcode = '22023';
  end if;

  return query
  select
    total.id,
    total.fiscal_year,
    total.metric_key,
    total.amount,
    total.currency::text,
    total.official_annex,
    total.official_label,
    total.official_column_label,
    total.official_account_code,
    total.official_account_label,
    artifact.source_url,
    artifact.sha256,
    artifact.retrieved_at,
    total.methodology_version
  from finance.siconfi_annual_totals as total
  join raw.raw_artifacts as artifact on artifact.id = total.source_artifact_id
  where total.validation_status = 'validated'
    and total.fiscal_year between fiscal_year_from and effective_year_to
    and not exists (
      select 1
      from finance.siconfi_annual_totals as successor
      where successor.supersedes_id = total.id
    )
    and exists (
      select 1
      from evidence.evidence_items as evidence_item
      where evidence_item.target_type = 'finance.siconfi_annual_totals'
        and evidence_item.target_id = total.id
        and evidence_item.raw_record_id = total.origin_raw_record_id
        and evidence_item.raw_artifact_id = total.source_artifact_id
        and evidence_item.is_primary
    )
  order by total.fiscal_year desc, total.metric_key
  limit page_size;
end;
$function$;

revoke all on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) from public;
grant execute on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) to anon, authenticated;

comment on table finance.siconfi_annual_totals is
  'Totais anuais literais da DCA/SICONFI, versionados e ligados a uma linha bruta e ao artefato oficial.';

comment on column finance.siconfi_annual_totals.amount is
  'Valor oficial em reais. Sinal negativo, quando publicado, é preservado sem reinterpretação.';

comment on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) is
  'Publica estágios anuais separados; não calcula saldo, superávit, déficit nem receita líquida.';

notify pgrst, 'reload schema';

commit;
