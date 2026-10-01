begin;

-- Quem recebe o dinheiro da Prefeitura (municipal-payment-recipients/1.0.0).
-- Soma exata das ordens de pagamento ORÇAMENTÁRIAS do portal (WebRun), pela
-- data do pagamento, na grade mais recente de cada mês. Grupo pela descrição
-- literal da natureza da despesa (regra fixa; o primeiro padrão vence;
-- descrição vazia ou inválida não vira "compras"). Credor só aparece pelo
-- nome quando o nome traz forma jurídica ou é ente público; pessoa física e
-- nome com CPF entram num agregado sem nome, em qualquer grupo. Revisão
-- contábil registrada no ADR 0095.

create function finance.payment_recipient_group_v1(p_nature text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select case
    when d ~ '^$|N[ÃA]O USAR'
      then 'nao_identificado'
    when d ~ 'SENTEN[ÇC]A|PRECAT[ÓO]RIO|DEP[ÓO]SITOS JUDICIAIS|HONOR[ÁA]RIOS SUCUMB'
      then 'judicial'
    -- Benefícios do servidor antes de "PREVID", que é encargo patronal.
    when d ~ ('APOSENTADORI|PENS[ÃAÕO]|BENEF[ÍI]CIOS? (PREVIDENCI|ASSISTENCI)'
        || '|AUX[ÍI]LIO.{0,3}(FUNERAL|NATALIDADE|CRECHE)')
      then 'pessoal'
    when d ~ 'D[ÍI]VIDA|AMORTIZA|JUROS (SOBRE|DA)'
      then 'divida'
    when d ~ 'PREVID|INSS|PIS/PASEP|OBRIGA[ÇC][ÕO]ES (TRIBUT|PATRONA)|ENCARGOS PATRONAIS|^TAXAS$'
      then 'tributos_encargos'
    when d ~ ('VENCIMENTO|SAL[ÁA]RIO|TEMPO DETERMINADO|SUBS[ÍI]DIO|SERVI[ÇC]O EXTRAORDIN'
        || '|PESSOAL REQUISITADO|PESSOAL CIVIL|VANTAGENS|\(PESSOAL|TRABALHISTA'
        || '|AUX[ÍI]LIO.{0,3}(ALIMENTA|TRANSPORTE)|DI[ÁA]RIAS|TRABALHOS DE CAMPO'
        || '|TRANSPORTE DE SERVIDORES')
      then 'pessoal'
    when d ~ 'AUX[ÍI]LIOS? FINANCEIROS? A (PESSOAS|ESTUDANTES|PESQUISADORES)|PREMIA[ÇC]'
      then 'auxilios'
    when d ~ ('SUBVEN[ÇC]|RATEIO|CONS[ÓO]RCIO|INSTITUI[ÇC][ÃA]O DE CAR[ÁA]TER'
        || '|^AUX[ÍI]LIOS$|^CONTRIBUI[ÇC][ÕO]ES$|^OUTRAS CONTR?IBUI[ÇC][ÕO]ES$')
      then 'transferencias'
    when d ~ 'RESTITUI|INDENIZA|RESSARCI'
      then 'restituicoes'
    else 'compras_servicos'
  end
  from (
    select upper(btrim(regexp_replace(coalesce(p_nature, ''), '^[0-9. ]+-\s*', ''))) as d
  ) as nature
$$;

-- Nome publicável: forma jurídica, ente público ou MEI (CNPJ-base no nome),
-- e nenhum CPF. Pessoa física sem marca fica no agregado.
create function finance.payment_creditor_is_entity_v1(p_name text)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $$
  select coalesce(
    n !~ '(^|[^0-9])[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}([^0-9]|$)'
    and (
      n ~ '^[0-9]{2}\.[0-9]{3}\.[0-9]{3} '
      or n ~ ('\m(LTDA|LIMITADA|EIRELL?I|EPP|ME|MEI|CIA|SPE|S\s*/\s*[AS]|S\.\s*A|SA'
        || '|COMPANHIA|EMPRESA|SOCIEDADE|ASSOCIACAO|FUNDACAO|INSTITUTO|CONSORCIO'
        || '|COOPERATIVA|SINDICATO|LIGA|MOVIMENTO|LAR|LOJA|IGREJA|PAROQUIA|DIOCESANA'
        || '|CARITAS|APAE|ORGANIZACAO|GRUPO|ESCRITORIO|ADVOCACIA|ADVOGADOS|ASSOCIADOS'
        || '|PREFEITURA|MUNICIPIO|MUNICIPAL|FUNDO|FOPAG|FOLHA DE PAGAMENTO'
        || '|MINISTERIO|SECRETARIA|GOVERNO|ESTADO|UNIAO|FEDERAL|AUTARQUIA|AGENCIA'
        || '|TRIBUNAL|CONSELHO|INSS|RECEITA|DETRAN|BANCO|CAIXA|CORREIOS'
        || '|HOSPITAL|CLINICA|LABORATORIO|FARMACIA|DROGARIA|POSTO|COMERCIO|COMERCIAL'
        || '|SERVICOS|SOLUTIONS|INDUSTRIA|DISTRIBUIDORA|CONSTRUTORA|ENGENHARIA'
        || '|ACADEMIA|ESCOLA|COLEGIO|UNIVERSIDADE|FACULDADE|EDITORA|PRODUCOES'
        || '|EVENTOS|TRANSPORTES?|LOCADORA|TELECOM|ENERGIA|SANEAMENTO)\M')
    ),
    false)
  from (
    select translate(upper(coalesce(p_name, '')),
      'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') as n
  ) as creditor
$$;

revoke all on function finance.payment_recipient_group_v1(text) from public, anon;
revoke all on function finance.payment_creditor_is_entity_v1(text) from public, anon;

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
security definer
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
  payments as materialized (
    select
      finance.payment_recipient_group_v1(line.payload ->> 'field1135675') as payment_group,
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
  commitment_years as (
    select distinct on (record.payload ->> 'field1144631')
      record.payload ->> 'field1144631' as commitment_key,
      right(record.payload ->> 'field1082407', 4) as commitment_year
    from raw.raw_records as record
    where record.record_type = 'municipal_commitment_webrun'
      and record.payload ->> 'field1144631' in (select payments.commitment_key from payments)
    order by record.payload ->> 'field1144631', record.collected_at desc
  ),
  by_creditor as (
    select
      payment.payment_group,
      case
        when finance.payment_creditor_is_entity_v1(payment.creditor) then payment.creditor
      end as creditor,
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
    'municipal-payment-recipients/1.0.0'::text
  from ranked
  join by_group on by_group.payment_group = ranked.payment_group
  cross join year_totals
  cross join bodies
  -- Até 150 nomes por grupo; o agregado sem nome sempre sai.
  where ranked.creditor is null or ranked.position <= 150
  order by by_group.paid desc, ranked.creditor is null, ranked.paid desc, ranked.creditor;
end;
$function$;

revoke all on function api.get_public_payment_recipients(integer) from public;
grant execute on function api.get_public_payment_recipients(integer)
  to anon, authenticated;

comment on function api.get_public_payment_recipients(integer) is
  'Ordens de pagamento orçamentárias do ano por grupo de natureza e credor (numeric exato); pessoa física só em agregado; restos a pagar e órgãos explícitos.';

commit;
