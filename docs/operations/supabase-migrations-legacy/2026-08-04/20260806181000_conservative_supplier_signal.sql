-- Um processo grande pode concentrar valor legitimamente. O sinal público só
-- aparece quando há recorrência entre processos ou recorrência + concentração.

alter function api.get_public_supplier_concentration(integer)
  rename to get_public_supplier_concentration_calculated;

create function api.get_public_supplier_concentration(page_size integer default 30)
returns table (
  supplier_key text,
  supplier_name text,
  supplier_type text,
  public_registration_number text,
  procurement_count integer,
  item_count integer,
  total_awarded_amount numeric,
  awarded_share numeric,
  first_result_date date,
  last_result_date date,
  attention_signal boolean,
  public_explanation text,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
  select
    calculated.supplier_key,
    calculated.supplier_name,
    calculated.supplier_type,
    calculated.public_registration_number,
    calculated.procurement_count,
    calculated.item_count,
    calculated.total_awarded_amount,
    calculated.awarded_share,
    calculated.first_result_date,
    calculated.last_result_date,
    (
      calculated.procurement_count >= 3
      or (calculated.procurement_count >= 2 and calculated.awarded_share >= 0.5)
    ),
    case
      when calculated.procurement_count >= 3
        or (calculated.procurement_count >= 2 and calculated.awarded_share >= 0.5)
        then 'Este fornecedor aparece em vários processos ou combina recorrência com parcela relevante do valor homologado na janela observada. É um sinal para contextualização, não prova de irregularidade.'
      else 'Resumo dos resultados homologados preservados no PNCP para esta janela. O número não mede qualidade, legalidade ou desempenho do fornecedor.'
    end,
    calculated.source_url,
    calculated.methodology_version
  from api.get_public_supplier_concentration_calculated(page_size) as calculated;
$function$;

revoke all on function api.get_public_supplier_concentration(integer) from public;
grant execute on function api.get_public_supplier_concentration(integer)
  to anon, authenticated;
