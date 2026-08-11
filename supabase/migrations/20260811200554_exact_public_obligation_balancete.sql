-- Vincula cada obrigação ao PDF exato e representa separadamente o valor
-- pago no mês, o acumulado anterior e o acumulado até o mês. Isso permite
-- publicar restos a pagar pagos sem apresentá-los como "dívida total".

alter table finance.public_obligations
  add column source_document_artifact_id uuid not null
    references raw.raw_artifacts(id),
  add column payments_prior_amount numeric(20,2)
    constraint public_obligations_payments_prior_amount_check check (
      payments_prior_amount is null or payments_prior_amount >= 0
    ),
  add column payments_to_date_amount numeric(20,2)
    constraint public_obligations_payments_to_date_amount_check check (
      payments_to_date_amount is null or payments_to_date_amount >= 0
    );

alter table finance.public_obligations
  drop constraint public_obligations_type_allowed,
  add constraint public_obligations_type_allowed check (
    obligation_type in (
      'loan',
      'precatorio',
      'accounts_payable',
      'restos_a_pagar_total',
      'restos_a_pagar_processados',
      'restos_a_pagar_nao_processados',
      'social_security',
      'court_order',
      'other'
    )
  ),
  add constraint public_obligations_payment_progression check (
    (
      payments_prior_amount is null
      or payments_amount is null
      or payments_to_date_amount is null
      or payments_prior_amount + payments_amount = payments_to_date_amount
    )
    and (
      obligation_type <> 'restos_a_pagar_total'
      or num_nonnulls(
        payments_prior_amount,
        payments_amount,
        payments_to_date_amount
      ) = 3
    )
  );

create index public_obligations_document_artifact_idx
  on finance.public_obligations (source_document_artifact_id);

-- Usa parâmetros posicionais para impedir que nomes iguais aos das colunas
-- transformem acidentalmente o filtro em "coluna = coluna".
create or replace function finance.has_direct_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from raw.raw_records as origin
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = $2
     and document.parent_artifact_id = source_artifact.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url = origin.payload ->> 'url'
    where origin.id = $1
      and origin.source_record_key is not null
  );
$function$;

create or replace function finance.resolve_document_origin(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns uuid
language sql
stable
security definer
set search_path = ''
as $function$
  select case
    when finance.has_direct_document_lineage($1, $2) then $1
    else (
      select lineage.effective_raw_record_id
      from finance.document_lineage_versions as lineage
      where lineage.document_artifact_id = $2
        and lineage.normalized_origin_raw_record_id = $1
        and lineage.lineage_status = 'corrected'
        and finance.has_direct_document_lineage(
          lineage.effective_raw_record_id,
          $2
        )
      order by lineage.version desc, lineage.created_at desc, lineage.id desc
      limit 1
    )
  end;
$function$;

create or replace function finance.has_exact_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select finance.resolve_document_origin($1, $2) is not null;
$function$;

revoke all on function finance.has_direct_document_lineage(uuid, uuid)
  from public, anon, authenticated;
revoke all on function finance.resolve_document_origin(uuid, uuid)
  from public, anon, authenticated;
revoke all on function finance.has_exact_document_lineage(uuid, uuid)
  from public, anon, authenticated;

create or replace function finance.enforce_public_obligation_document_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if not coalesce(
    finance.has_exact_document_lineage(
      new.origin_raw_record_id,
      new.source_document_artifact_id
    ),
    false
  ) then
    raise exception 'documento nao corresponde ao registro bruto da obrigacao'
      using errcode = '23514';
  end if;
  return new;
end;
$function$;

revoke all on function finance.enforce_public_obligation_document_lineage()
  from public, anon, authenticated;

create trigger enforce_document_lineage
before insert on finance.public_obligations
for each row execute function finance.enforce_public_obligation_document_lineage();

drop function api.get_public_obligations(integer, integer, text);

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
  payments_prior_amount numeric(20,2),
  payments_amount numeric(20,2),
  payments_to_date_amount numeric(20,2),
  closing_balance numeric(20,2),
  status text,
  validation_state text,
  source_url text,
  artifact_sha256 text,
  source_retrieved_at timestamptz,
  document_source_url text,
  document_artifact_sha256 text,
  document_retrieved_at timestamptz,
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
    'restos_a_pagar_total',
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
    obligation.payments_prior_amount,
    obligation.payments_amount,
    obligation.payments_to_date_amount,
    obligation.closing_balance,
    obligation.status,
    obligation.validation_state,
    source_artifact.source_url,
    source_artifact.sha256,
    source_artifact.retrieved_at,
    document.source_url,
    document.sha256,
    document.retrieved_at,
    obligation.methodology_version
  from finance.public_obligations as obligation
  join raw.raw_records as origin
    on origin.id = obligation.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = obligation.source_document_artifact_id
  where obligation.validation_state in ('validated', 'reconciled')
    and finance.has_exact_document_lineage(
      obligation.origin_raw_record_id,
      obligation.source_document_artifact_id
    )
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

comment on column finance.public_obligations.payments_amount is
  'Valor pago no período do registro; não é saldo nem dívida total.';
comment on column finance.public_obligations.payments_prior_amount is
  'Valor acumulado pago até o período imediatamente anterior, quando declarado.';
comment on column finance.public_obligations.payments_to_date_amount is
  'Valor acumulado pago até o fim do período, quando declarado.';
comment on function api.get_public_obligations(integer, integer, text) is
  'Obrigações validadas com PDF exato; pagamentos de restos a pagar não representam dívida total.';
