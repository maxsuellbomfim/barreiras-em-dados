begin;

set local statement_timeout = '300s';
set local lock_timeout = '5s';

-- municipal-payment-recipients/1.1.0: credor nomeado ganha CNPJ, razão social e
-- natureza jurídica do cadastro da Receita quando o empenho pago está ligado a
-- contrato confirmado e todas as ligações do credor apontam o mesmo CNPJ. Sem
-- ligação confirmada, nada é inferido pelo nome.

drop function api.get_public_payment_recipients(integer);
drop function finance.compute_payment_recipients(integer);

alter table finance.payment_recipient_snapshots
  add column registry_cnpj text,
  add column registry_legal_name text,
  add column registry_legal_nature text,
  add column registry_month text;

create function finance.compute_payment_recipients(p_year integer)
returns table (
  payment_group text,
  creditor_name text,
  creditors integer,
  payments integer,
  paid_amount text,
  first_payment_date date,
  last_payment_date date,
  main_nature text,
  grid_artifact_sha256 text,
  registry_cnpj text,
  registry_legal_name text,
  registry_legal_nature text,
  registry_month text,
  group_payments integer,
  group_creditors integer,
  group_paid_amount text,
  year_payments integer,
  year_paid_amount text,
  year_prior_commitment_amount text,
  year_uncollected_commitment_amount text,
  year_bodies jsonb,
  year_grid_months integer,
  year_unreadable_rows integer,
  year_excluded_rows integer,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
set search_path = ''
as $function$
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;

  return query
  with grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id,
      artifact.sha256
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
      and artifact.metadata -> 'cursor' ->> 'month' like p_year::text || '-%'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  lines as materialized (
    select
      record.payload,
      grid.sha256,
      record.payload ->> 'field1082592'
        ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$' as readable,
      -- Só orçamentária, chave O- e data do pagamento no ano pedido.
      coalesce(
        record.payload ->> 'field1082594' = 'Orçamentária'
        and record.payload ->> 'field1082596' ~ '^O-[0-9]+$'
        and record.payload ->> 'field1082587' ~ ('^[0-9]{2}/[0-9]{2}/' || p_year::text || '$'),
        false) as in_scope
    from raw.raw_records as record
    join grids as grid on grid.id = record.raw_artifact_id
    where record.record_type = 'municipal_payment_webrun'
  ),
  payment_lines as materialized (
    select
      line.payload ->> 'field1135675' as nature_text,
      nullif(btrim(line.payload ->> 'field1144925'), '') as creditor,
      upper(btrim(regexp_replace(
        coalesce(line.payload ->> 'field1135675', ''), '^[0-9. ]+-\s*', ''))) as nature,
      coalesce(nullif(btrim(line.payload ->> 'field1082598'), ''), 'ÓRGÃO NÃO INFORMADO')
        as public_body,
      line.payload ->> 'field1082596' as commitment_key,
      to_date(line.payload ->> 'field1082587', 'DD/MM/YYYY') as paid_on,
      replace(replace(line.payload ->> 'field1082592', '.', ''), ',', '.')::numeric as amount,
      line.sha256
    from lines as line
    where line.readable and line.in_scope
  ),
  natures as materialized (
    select distinct
      payment_line.nature_text,
      finance.payment_recipient_group_v1(payment_line.nature_text) as payment_group
    from payment_lines as payment_line
  ),
  creditors as materialized (
    select distinct
      payment_line.creditor,
      finance.payment_creditor_is_entity_v1(payment_line.creditor) as is_entity
    from payment_lines as payment_line
  ),
  payments as materialized (
    select payment_line.*, nature.payment_group, creditor.is_entity
    from payment_lines as payment_line
    join natures as nature
      on nature.nature_text is not distinct from payment_line.nature_text
    join creditors as creditor
      on creditor.creditor is not distinct from payment_line.creditor
  ),
  commitment_years as (
    select distinct on (record.payload ->> 'field1144631')
      record.payload ->> 'field1144631' as commitment_key,
      right(record.payload ->> 'field1082407', 4) as commitment_year
    from raw.raw_records as record
    where record.record_type = 'municipal_commitment_webrun'
      and record.payload ->> 'field1144631' in (select payments.commitment_key from payments)
    order by record.payload ->> 'field1144631', record.collected_at desc
  ),
  -- 1.1.0: CNPJ do credor pelo contrato de uma ligação confirmada (regra
  -- automática ADR 0086 ou decisão aprovada vigente) e o cadastro da Receita
  -- (ADR 0093). Só sai quando todas as ligações do credor dão o mesmo CNPJ.
  latest_reviews as (
    select distinct on (review.target_id)
      review.target_id,
      review.decision,
      review.checklist ->> 'contract_raw_record_id' as contract_raw_record_id
    from editorial.editorial_reviews as review
    where review.target_type = 'finance.commitment_contract_links'
    order by review.target_id, review.reviewed_at desc, review.id desc
  ),
  confirmed_contracts as (
    select link.commitment_key, link.contract_raw_record_id
    from finance.commitment_contract_links as link
    where link.state = 'ligado'
      and link.commitment_key in (select payments.commitment_key from payments)
    union
    select link.commitment_key, review.contract_raw_record_id::uuid
    from finance.commitment_contract_links as link
    join latest_reviews as review
      on review.target_id = link.id
     and review.decision = 'approved'
     and review.contract_raw_record_id ~ '^[0-9a-f-]{36}$'
    where link.state = 'citacao_sem_confirmacao'
      and link.commitment_key in (select payments.commitment_key from payments)
  ),
  creditor_registry as (
    select
      payment.creditor,
      min(registry.cnpj) as cnpj,
      min(registry.razao_social) as legal_name,
      min(registry.natureza_juridica_descricao) as legal_nature,
      min(registry.registry_month) as registry_month
    from payments as payment
    join confirmed_contracts as confirmed
      on confirmed.commitment_key = payment.commitment_key
    join raw.raw_records as contract
      on contract.id = confirmed.contract_raw_record_id
    join finance.cnpj_registry_latest() as registry
      on registry.cnpj = regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g')
    where payment.is_entity
    group by payment.creditor
    having count(distinct registry.cnpj) = 1
  ),
  by_creditor as (
    select
      payment.payment_group,
      case when payment.is_entity then payment.creditor end as creditor,
      count(distinct coalesce(payment.creditor, ''))::integer as creditors,
      count(*)::integer as payments,
      sum(payment.amount) as paid,
      min(payment.paid_on) as first_date,
      max(payment.paid_on) as last_date,
      mode() within group (order by payment.nature) as main_nature,
      (array_agg(payment.sha256 order by payment.paid_on desc))[1] as sha256
    from payments as payment
    group by 1, 2
  ),
  by_group as (
    select
      payment.payment_group,
      count(*)::integer as payments,
      count(distinct coalesce(payment.creditor, ''))::integer as creditors,
      sum(payment.amount) as paid
    from payments as payment
    group by 1
  ),
  ranked as (
    select
      by_creditor.*,
      row_number() over (
        partition by by_creditor.payment_group, by_creditor.creditor is null
        order by by_creditor.paid desc, by_creditor.creditor
      ) as position
    from by_creditor
  ),
  bodies as (
    select jsonb_agg(
      jsonb_build_object(
        'public_body', body.public_body,
        'payments', body.payments,
        'paid_amount', to_char(body.paid, 'FM999999999990.00'))
      order by body.paid desc, body.public_body) as list
    from (
      select payment.public_body, count(*)::integer as payments, sum(payment.amount) as paid
      from payments as payment
      group by 1
    ) as body
  ),
  year_totals as (
    select
      (select count(*)::integer from payments) as payments,
      (select sum(amount) from payments) as paid,
      (select coalesce(sum(payment.amount), 0)
         from payments as payment
         join commitment_years as commitment using (commitment_key)
         where commitment.commitment_year < p_year::text) as prior,
      (select coalesce(sum(payment.amount), 0)
         from payments as payment
         where not exists (
           select 1 from commitment_years as commitment
           where commitment.commitment_key = payment.commitment_key)) as uncollected,
      (select count(*)::integer from grids) as grid_months,
      (select count(*)::integer from lines where lines.in_scope and not lines.readable)
        as unreadable,
      (select count(*)::integer from lines where not lines.in_scope) as excluded
  )
  select
    ranked.payment_group,
    editorial.mask_cpf_v1(ranked.creditor),
    ranked.creditors,
    ranked.payments,
    to_char(ranked.paid, 'FM999999999990.00'),
    ranked.first_date,
    ranked.last_date,
    ranked.main_nature,
    ranked.sha256,
    creditor_registry.cnpj,
    creditor_registry.legal_name,
    creditor_registry.legal_nature,
    creditor_registry.registry_month,
    by_group.payments,
    by_group.creditors,
    to_char(by_group.paid, 'FM999999999990.00'),
    year_totals.payments,
    to_char(year_totals.paid, 'FM999999999990.00'),
    to_char(year_totals.prior, 'FM999999999990.00'),
    to_char(year_totals.uncollected, 'FM999999999990.00'),
    bodies.list,
    year_totals.grid_months,
    year_totals.unreadable,
    year_totals.excluded,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'municipal-payment-recipients/1.1.0'::text
  from ranked
  join by_group on by_group.payment_group = ranked.payment_group
  cross join year_totals
  cross join bodies
  left join creditor_registry on creditor_registry.creditor = ranked.creditor
  -- Até 150 nomes por grupo; o agregado sem nome sempre sai.
  where ranked.creditor is null or ranked.position <= 150
  order by by_group.paid desc, ranked.creditor is null, ranked.paid desc, ranked.creditor;
end;
$function$;

revoke all on function finance.compute_payment_recipients(integer)
  from public, anon, authenticated;

create or replace function finance.refresh_payment_recipients()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  refreshed integer := 0;
  year_rows integer;
  target_year integer;
  content_sha256 text;
  refreshed_on timestamptz := now();
begin
  perform pg_advisory_xact_lock(hashtext('finance.payment_recipient_snapshots'));

  for target_year in
    select distinct substr(artifact.metadata -> 'cursor' ->> 'month', 1, 4)::integer
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
      and artifact.metadata -> 'cursor' ->> 'month' ~ '^20[0-9]{2}-[0-9]{2}$'
      and substr(artifact.metadata -> 'cursor' ->> 'month', 1, 4)::integer >= 2024
    order by 1
  loop
    delete from finance.payment_recipient_snapshots where fiscal_year = target_year;
    insert into finance.payment_recipient_snapshots (
      fiscal_year, row_order, payment_group, creditor_name, creditors, payments, paid_amount,
      first_payment_date, last_payment_date, main_nature, grid_artifact_sha256,
      registry_cnpj, registry_legal_name, registry_legal_nature, registry_month,
      group_payments, group_creditors, group_paid_amount, year_payments, year_paid_amount,
      year_prior_commitment_amount, year_uncollected_commitment_amount, year_bodies,
      year_grid_months, year_unreadable_rows, year_excluded_rows, source_page_url,
      methodology_version, refreshed_at)
    select target_year, computed.ordinality::integer, computed.payment_group, computed.creditor_name, computed.creditors, computed.payments, computed.paid_amount, computed.first_payment_date, computed.last_payment_date, computed.main_nature, computed.grid_artifact_sha256, computed.registry_cnpj, computed.registry_legal_name, computed.registry_legal_nature, computed.registry_month, computed.group_payments, computed.group_creditors, computed.group_paid_amount, computed.year_payments, computed.year_paid_amount, computed.year_prior_commitment_amount, computed.year_uncollected_commitment_amount, computed.year_bodies, computed.year_grid_months, computed.year_unreadable_rows, computed.year_excluded_rows, computed.source_page_url, computed.methodology_version, refreshed_on
    from finance.compute_payment_recipients(target_year) with ordinality as computed;
    get diagnostics year_rows = row_count;
    refreshed := refreshed + year_rows;
  end loop;

  select encode(sha256(convert_to(coalesce(jsonb_agg(
      to_jsonb(snapshot) - 'refreshed_at' order by snapshot.fiscal_year, snapshot.row_order
    ), '[]'::jsonb)::text, 'UTF8')), 'hex')
  into content_sha256
  from finance.payment_recipient_snapshots as snapshot;

  insert into audit.audit_events (
    actor_type, actor_subject, action, target_type, target_id, after_state, metadata
  ) values (
    'worker',
    'payment-recipients',
    'source_snapshot.refreshed',
    'finance.payment_recipient_snapshots',
    null,
    jsonb_build_object('row_count', refreshed, 'content_sha256', content_sha256),
    jsonb_build_object(
      'methodology_version', 'municipal-payment-recipients/1.1.0',
      'records_deleted', false
    )
  );

  return refreshed;
end;
$function$;

create function api.get_public_payment_recipients(p_year integer)
returns table (
  payment_group text,
  creditor_name text,
  creditors integer,
  payments integer,
  paid_amount text,
  first_payment_date date,
  last_payment_date date,
  main_nature text,
  grid_artifact_sha256 text,
  registry_cnpj text,
  registry_legal_name text,
  registry_legal_nature text,
  registry_month text,
  group_payments integer,
  group_creditors integer,
  group_paid_amount text,
  year_payments integer,
  year_paid_amount text,
  year_prior_commitment_amount text,
  year_uncollected_commitment_amount text,
  year_bodies jsonb,
  year_grid_months integer,
  year_unreadable_rows integer,
  year_excluded_rows integer,
  source_page_url text,
  methodology_version text,
  refreshed_at timestamptz
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;

  return query
  select
    snapshot.payment_group,
    snapshot.creditor_name,
    snapshot.creditors,
    snapshot.payments,
    snapshot.paid_amount,
    snapshot.first_payment_date,
    snapshot.last_payment_date,
    snapshot.main_nature,
    snapshot.grid_artifact_sha256,
    snapshot.registry_cnpj,
    snapshot.registry_legal_name,
    snapshot.registry_legal_nature,
    snapshot.registry_month,
    snapshot.group_payments,
    snapshot.group_creditors,
    snapshot.group_paid_amount,
    snapshot.year_payments,
    snapshot.year_paid_amount,
    snapshot.year_prior_commitment_amount,
    snapshot.year_uncollected_commitment_amount,
    snapshot.year_bodies,
    snapshot.year_grid_months,
    snapshot.year_unreadable_rows,
    snapshot.year_excluded_rows,
    snapshot.source_page_url,
    snapshot.methodology_version,
    snapshot.refreshed_at
  from finance.payment_recipient_snapshots as snapshot
  where snapshot.fiscal_year = p_year
  order by snapshot.row_order;
end;
$function$;

revoke all on function api.get_public_payment_recipients(integer) from public;
grant execute on function api.get_public_payment_recipients(integer)
  to anon, authenticated;

comment on function api.get_public_payment_recipients(integer) is
  'Ordens de pagamento orçamentárias do ano por grupo de natureza e credor (numeric exato), com CNPJ do cadastro da Receita quando há contrato confirmado; pessoa física só em agregado.';

select finance.refresh_payment_recipients();

commit;
