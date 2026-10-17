begin;

-- Dívida consolidada (/financas/divida): CTE de linhas do quadrimestre
-- passa a ser materializada (0,85 s → poucos ms). Mesmo resultado.

create or replace function api.get_public_debt_statements()
returns table (
  fiscal_year integer,
  period integer,
  period_end date,
  consolidated_debt text,
  deductions text,
  net_consolidated_debt text,
  adjusted_net_current_revenue text,
  net_debt_revenue_percent text,
  senate_limit text,
  alert_limit text,
  composition jsonb,
  artifact_sha256 text,
  retrieved_at timestamptz,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
  with lines as materialized (
    select
      (record.payload ->> 'exercicio')::integer as fiscal_year,
      (record.payload ->> 'periodo')::integer as period,
      record.payload,
      record.record_index,
      artifact.id as artifact_id,
      artifact.sha256,
      artifact.retrieved_at
    from raw.raw_records as record
    join raw.raw_artifacts as artifact on artifact.id = record.raw_artifact_id
    where record.record_type = 'siconfi_rgf_annex2_line'
      and record.payload ->> 'anexo' = 'RGF-Anexo 02'
      and record.payload ->> 'co_poder' = 'E'
      and record.payload ->> 'exercicio' ~ '^[0-9]{4}$'
      and record.payload ->> 'periodo' in ('1', '2', '3')
  ),
  -- Retificação no SICONFI gera nova página: vale a coleta mais recente.
  latest as (
    select distinct on (lines.fiscal_year, lines.period)
      lines.fiscal_year, lines.period, lines.artifact_id, lines.sha256,
      lines.retrieved_at
    from lines
    order by lines.fiscal_year, lines.period, lines.retrieved_at desc,
      lines.artifact_id desc
  ),
  -- Só a coluna acumulada do próprio quadrimestre ("Até o 3º Quadrimestre").
  -- materialized: sem isso o planejador reavaliava o regex de coluna em
  -- cada volta do nested loop (529 varreduras, 0,85 s em 17/10/2026).
  period_lines as materialized (
    select lines.*
    from lines
    join latest
      on latest.artifact_id = lines.artifact_id
     and latest.fiscal_year = lines.fiscal_year
     and latest.period = lines.period
    where lines.payload ->> 'coluna' ~ ('^At[ée] o ' || lines.period::text || '[^0-9]')
  )
  select
    latest.fiscal_year,
    latest.period,
    (make_date(latest.fiscal_year, (array[4, 8, 12])[latest.period], 1)
      + interval '1 month - 1 day')::date,
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DividaConsolidada'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DeducoesDaDividaConsolidada'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DividaConsolidadaLiquida'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta'
        = 'ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'PercentualDaDCLSobreARCL'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'LimiteDefinidoPorResolucaoDoSenadoFederal'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'LimiteDeAlerta'),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'code', line.payload ->> 'cod_conta',
          'account', line.payload ->> 'conta',
          'value', line.payload ->> 'valor'
        )
        order by line.record_index
      ) filter (where line.payload is not null),
      '[]'::jsonb
    ),
    latest.sha256,
    latest.retrieved_at,
    'https://siconfi.tesouro.gov.br/siconfi/pages/public/consulta_finbra_rgf/finbra_rgf_list.jsf'::text,
    'municipal-debt-rgf-annex2/1.0.0'::text
  from latest
  left join period_lines as line
    on line.artifact_id = latest.artifact_id
   and line.fiscal_year = latest.fiscal_year
   and line.period = latest.period
  group by latest.fiscal_year, latest.period, latest.sha256, latest.retrieved_at
  order by latest.fiscal_year desc, latest.period desc;
$function$;

notify pgrst, 'reload schema';

commit;
