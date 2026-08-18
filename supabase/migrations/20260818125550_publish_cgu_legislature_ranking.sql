begin;

-- Serie CGU agrupada por legislatura federal, publicada como bloco separado
-- dentro da comparacao por mandato. Continua uma serie propria: ordena por
-- empenhado, mostra o pago efetivo (pago + restos pagos) e nunca se soma ao
-- valor destinado do Transferegov. Exercicios fora das legislaturas
-- cadastradas e o ano de transicao 2023 permanecem visiveis apenas na aba
-- Execucao federal, como o ADR 0069 preve.

create function api.get_public_cgu_federal_amendment_legislature_ranking(
  page_size_per_legislature integer default 10
)
returns table (
  legislature_number smallint,
  legislature_label text,
  full_fiscal_year_from smallint,
  full_fiscal_year_to smallint,
  author_scope text,
  rank_position integer,
  author_kind text,
  author_key text,
  author_name text,
  author_code text,
  amendment_count integer,
  committed_amount numeric(20,2),
  effective_paid_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  ranking_amount_stage text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if page_size_per_legislature is null
    or page_size_per_legislature < 1
    or page_size_per_legislature > 10
  then
    raise exception 'limite por legislatura deve estar entre 1 e 10'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      term.legislature_number,
      term.legislature_label,
      term.full_fiscal_year_from,
      term.full_fiscal_year_to,
      case
        when execution.author_kind = 'person' then 'person'
        else 'collective'
      end as author_scope,
      execution.author_kind,
      execution.author_key,
      (array_agg(
        execution.author_name
        order by execution.fiscal_year desc, execution.raw_record_id desc
      ))[1] as author_name,
      (array_agg(
        execution.author_code
        order by execution.fiscal_year desc, execution.raw_record_id desc
      ))[1] as author_code,
      count(*)::integer as amendment_count,
      sum(execution.committed_amount)::numeric(20,2) as committed_amount,
      sum(execution.effective_paid_amount)::numeric(20,2)
        as effective_paid_amount,
      min(execution.fiscal_year)::smallint as first_year,
      max(execution.fiscal_year)::smallint as last_year
    from political.legislative_terms as term
    join territory.cgu_federal_amendment_executions as execution
      on execution.fiscal_year
        between term.full_fiscal_year_from and term.full_fiscal_year_to
    where term.sphere = 'federal'
      and execution.author_identified
      and execution.author_kind in (
        'person', 'commission', 'bench', 'collective'
      )
    group by
      term.legislature_number,
      term.legislature_label,
      term.full_fiscal_year_from,
      term.full_fiscal_year_to,
      case
        when execution.author_kind = 'person' then 'person'
        else 'collective'
      end,
      execution.author_kind,
      execution.author_key
  ), ranked as (
    select
      row_number() over (
        partition by grouped.legislature_number, grouped.author_scope
        order by
          grouped.committed_amount desc,
          grouped.effective_paid_amount desc,
          grouped.author_name
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.legislature_number,
    ranked.legislature_label,
    ranked.full_fiscal_year_from,
    ranked.full_fiscal_year_to,
    ranked.author_scope,
    ranked.rank_position,
    ranked.author_kind,
    ranked.author_key,
    ranked.author_name,
    ranked.author_code,
    ranked.amendment_count,
    ranked.committed_amount,
    ranked.effective_paid_amount,
    ranked.first_year,
    ranked.last_year,
    'committed'::text,
    'cgu-federal-amendment-legislature-ranking/1.0.0'::text
  from ranked
  where ranked.rank_position <= page_size_per_legislature
  order by
    ranked.legislature_number desc,
    ranked.author_scope,
    ranked.rank_position;
end;
$$;

revoke all on function api.get_public_cgu_federal_amendment_legislature_ranking(
  integer
) from public;

grant execute on function
  api.get_public_cgu_federal_amendment_legislature_ranking(integer)
  to anon, authenticated;

comment on function
  api.get_public_cgu_federal_amendment_legislature_ranking(integer) is
  'Serie CGU por legislatura federal: empenhado e pago efetivo separados do valor destinado do Transferegov; autoria nao identificada e anos fora das janelas ficam so na aba da CGU.';

notify pgrst, 'reload schema';

commit;
