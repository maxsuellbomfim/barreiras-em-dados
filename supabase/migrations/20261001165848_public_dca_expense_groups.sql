begin;

-- Pago e liquidado por grupo de natureza da despesa, como declarados pela
-- Prefeitura na DCA do SICONFI (Anexo I-D), em valores literais da coleta mais
-- recente do exercício (siconfi-dca-expense-groups/1.0.0). Serve para o
-- cidadão comparar, lado a lado, com as ordens de pagamento do portal; a
-- plataforma não atribui causa às diferenças.

create function api.get_public_dca_expense_groups(p_year integer)
returns table (
  fiscal_year integer,
  account_code text,
  account_label text,
  paid_amount text,
  liquidated_amount text,
  artifact_sha256 text,
  retrieved_at timestamptz,
  source_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if p_year is null or p_year < 2015 or p_year > 2100 then
    raise exception 'ano deve estar entre 2015 e 2100' using errcode = '22023';
  end if;

  return query
  with lines as materialized (
    select
      record.payload,
      artifact.id as artifact_id,
      artifact.sha256,
      artifact.retrieved_at,
      artifact.source_url
    from raw.raw_records as record
    join raw.raw_artifacts as artifact on artifact.id = record.raw_artifact_id
    where record.record_type = 'siconfi_dca_line'
      and record.payload ->> 'anexo' = 'DCA-Anexo I-D'
      and record.payload ->> 'exercicio' = p_year::text
      and record.payload ->> 'coluna' in ('Despesas Pagas', 'Despesas Liquidadas')
      -- Total e grupos de natureza (3.1 pessoal, 3.2 juros, 3.3 outras
      -- correntes, 4.4 investimentos, 4.5 inversões, 4.6 amortização).
      and record.payload ->> 'cod_conta' in (
        'TotalDespesas', 'DO3.1.00.00.00.00', 'DO3.2.00.00.00.00', 'DO3.3.00.00.00.00',
        'DO4.4.00.00.00.00', 'DO4.5.00.00.00.00', 'DO4.6.00.00.00.00')
      and record.payload ->> 'valor' ~ '^-?[0-9]+(\.[0-9]+)?$'
  ),
  -- Retificação no SICONFI gera nova coleta: vale a linha mais recente de cada
  -- conta e coluna (também se a resposta vier em várias páginas).
  latest as (
    select distinct on (lines.payload ->> 'cod_conta', lines.payload ->> 'coluna')
      lines.*
    from lines
    order by lines.payload ->> 'cod_conta', lines.payload ->> 'coluna',
      lines.retrieved_at desc, lines.artifact_id desc
  )
  select
    p_year,
    line.payload ->> 'cod_conta',
    min(line.payload ->> 'conta'),
    to_char(max((line.payload ->> 'valor')::numeric)
      filter (where line.payload ->> 'coluna' = 'Despesas Pagas'), 'FM999999999990.00'),
    to_char(max((line.payload ->> 'valor')::numeric)
      filter (where line.payload ->> 'coluna' = 'Despesas Liquidadas'), 'FM999999999990.00'),
    (array_agg(line.sha256 order by line.retrieved_at desc))[1],
    max(line.retrieved_at),
    (array_agg(line.source_url order by line.retrieved_at desc))[1],
    'siconfi-dca-expense-groups/1.0.0'::text
  from latest as line
  group by line.payload ->> 'cod_conta'
  order by case line.payload ->> 'cod_conta' when 'TotalDespesas' then 1 else 0 end,
    line.payload ->> 'cod_conta';
end;
$function$;

revoke all on function api.get_public_dca_expense_groups(integer) from public;
grant execute on function api.get_public_dca_expense_groups(integer) to anon, authenticated;

comment on function api.get_public_dca_expense_groups(integer) is
  'Pago e liquidado por grupo de natureza da despesa declarados na DCA (Anexo I-D) do exercício, literais da coleta mais recente, com hash do artefato.';

commit;
