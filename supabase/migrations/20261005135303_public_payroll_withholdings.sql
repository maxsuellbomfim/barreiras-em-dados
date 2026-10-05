begin;

-- municipal-payroll-withholdings/1.0.0: retenções da folha (INSS do servidor,
-- consignados, contribuições sindicais, pensão alimentícia) como a Prefeitura
-- as publica: empenhos do tipo Extra-Orçamentária no sistema de despesas.
-- O portal não publica liquidação nem pagamento para esses empenhos; a função
-- conta, pela chave oficial, quantos pagamentos publicados apontam para eles.
-- Pensão alimentícia e credores pessoa física são somados sem nome: o
-- histórico traz o nome do servidor e o do beneficiário (desconto pessoal).

create function finance.payroll_withholding_v1(p_history text)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $function$
  select coalesce(
    p_history ~* 'reten|consign|segurado|sindical|previd|INSS|pens[ãa]o'
    and p_history ~* 'folha|pens[ãa]o'
    -- INSS/IR retidos de notas fiscais de fornecedores ficam de fora.
    and p_history !~* 'nota fiscal|\mNF\M|empresa',
    false)
$function$;

create function api.get_public_payroll_withholdings(p_year integer)
returns table (
  creditor_name text,
  commitments integer,
  amount text,
  reversal_amount text,
  first_commitment_date date,
  last_commitment_date date,
  latest_commitment_key text,
  grid_artifact_sha256 text,
  year_commitments integer,
  year_amount text,
  year_reversal_amount text,
  year_grid_months integer,
  year_linked_payments integer,
  year_months jsonb,
  source_page_url text,
  methodology_version text
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
  with commitment_grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id,
      artifact.sha256
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-commitments-webrun-grid'
      and artifact.metadata -> 'cursor' ->> 'month' like p_year::text || '-%'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  payment_grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  lines as materialized (
    select
      record.payload ->> 'field1144631' as commitment_key,
      to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') as issue_date,
      replace(replace(record.payload ->> 'field1082412', '.', ''), ',', '.')::numeric
        as amount,
      case
        when record.payload ->> 'field1144634' !~* 'pens[ãa]o'
          and finance.payment_creditor_is_entity_v1(record.payload ->> 'field1144629')
        then btrim(record.payload ->> 'field1144629')
      end as creditor_name,
      grid.sha256
    from raw.raw_records as record
    join commitment_grids as grid on grid.id = record.raw_artifact_id
    where record.record_type = 'municipal_commitment_webrun'
      and record.payload ->> 'field1082409' ~* '^extra'
      and record.payload ->> 'field1082407' ~ ('^[0-9]{2}/[0-9]{2}/' || p_year::text || '$')
      and record.payload ->> 'field1144631' ~ '^E-[0-9]+$'
      and record.payload ->> 'field1082412'
        ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$'
      and finance.payroll_withholding_v1(record.payload ->> 'field1144634')
  ),
  grouped as (
    select
      lines.creditor_name,
      count(*)::integer as commitments,
      sum(lines.amount) as amount,
      coalesce(sum(lines.amount) filter (where lines.amount < 0), 0) as reversals,
      min(lines.issue_date) as first_date,
      max(lines.issue_date) as last_date,
      (array_agg(lines.commitment_key
        order by lines.issue_date desc, lines.commitment_key desc))[1] as latest_key,
      (array_agg(lines.sha256
        order by lines.issue_date desc, lines.commitment_key desc))[1] as latest_sha256
    from lines
    group by 1
  ),
  months as (
    select jsonb_agg(
      jsonb_build_object(
        'month', month_rows.month,
        'commitments', month_rows.commitments,
        'amount', to_char(month_rows.amount, 'FM999999999990.00'))
      order by month_rows.month) as months
    from (
      select
        to_char(lines.issue_date, 'YYYY-MM') as month,
        count(*)::integer as commitments,
        sum(lines.amount) as amount
      from lines
      group by 1
    ) as month_rows
  ),
  totals as (
    select
      count(*)::integer as commitments,
      sum(lines.amount) as amount,
      coalesce(sum(lines.amount) filter (where lines.amount < 0), 0) as reversals,
      (
        select count(*)::integer
        from raw.raw_records as payment
        join payment_grids as grid on grid.id = payment.raw_artifact_id
        where payment.record_type = 'municipal_payment_webrun'
          and payment.payload ->> 'field1082596' in (select l.commitment_key from lines as l)
      ) as linked_payments
    from lines
  )
  select
    grouped.creditor_name,
    grouped.commitments,
    to_char(grouped.amount, 'FM999999999990.00'),
    to_char(grouped.reversals, 'FM999999999990.00'),
    grouped.first_date,
    grouped.last_date,
    grouped.latest_key,
    grouped.latest_sha256,
    totals.commitments,
    to_char(totals.amount, 'FM999999999990.00'),
    to_char(totals.reversals, 'FM999999999990.00'),
    (select count(*)::integer from commitment_grids),
    totals.linked_payments,
    months.months,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'municipal-payroll-withholdings/1.0.0'::text
  from grouped
  cross join totals
  cross join months
  order by grouped.amount desc, grouped.creditor_name nulls last
  limit 500;
end;
$function$;

revoke all on function api.get_public_payroll_withholdings(integer) from public;
grant execute on function api.get_public_payroll_withholdings(integer)
  to anon, authenticated;

comment on function api.get_public_payroll_withholdings(integer) is
  'Retenções da folha publicadas como empenhos extraorçamentários no ano, por credor (pessoas físicas e pensão alimentícia somadas sem nome), com totais mensais e a contagem de pagamentos publicados que apontam para esses empenhos.';

commit;
