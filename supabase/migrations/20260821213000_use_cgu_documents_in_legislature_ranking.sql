begin;

-- O ranking por legislatura passa a nascer exclusivamente da serie documental
-- da CGU. O ano da emenda define a legislatura; a data/ano do documento apenas
-- prova quando a execucao ocorreu. O retrato agregado antigo e o Transferegov
-- continuam publicados em series separadas e nunca entram nestes totais.

drop function if exists
  api.get_public_cgu_federal_amendment_legislature_ranking(integer);

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
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
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
  with candidates as (
    select
      term.legislature_number,
      term.legislature_label,
      term.full_fiscal_year_from,
      term.full_fiscal_year_to,
      case
        when document.author_kind = 'person' then 'person'
        else 'collective'
      end as author_scope,
      document.author_kind,
      document.author_key,
      document.author_name,
      document.author_code,
      document.amendment_code,
      document.amendment_year,
      document.document_date,
      document.raw_record_id,
      document.expense_stage,
      document.committed_amount,
      document.paid_amount,
      identity_match.representative_source_kind,
      identity_match.representative_external_id,
      identity_match.representative_profile_url
    from political.legislative_terms as term
    join territory.cgu_federal_amendment_documents as document
      on document.amendment_year
        between term.full_fiscal_year_from and term.full_fiscal_year_to
    left join lateral (
      select
        case when count(*) = 1
          then max(crosswalk.representative_source_kind)
        end as representative_source_kind,
        case when count(*) = 1
          then max(crosswalk.representative_external_id)
        end as representative_external_id,
        case when count(*) = 1
          then max(crosswalk.representative_profile_url)
        end as representative_profile_url
      from political.parliamentary_author_code_crosswalk as crosswalk
      where document.author_kind = 'person'
        and crosswalk.source_system = 'federal_amendment_author_code'
        and crosswalk.source_author_code = document.author_code
        and document.amendment_year
          between crosswalk.valid_from_year and crosswalk.valid_to_year
        and crosswalk.review_status = 'approved'
        and lower(btrim(crosswalk.source_author_name)) = document.author_key
    ) as identity_match on true
    where term.sphere = 'federal'
      and document.author_kind in ('person', 'commission', 'bench')
  ), grouped as (
    select
      candidates.legislature_number,
      candidates.legislature_label,
      candidates.full_fiscal_year_from,
      candidates.full_fiscal_year_to,
      candidates.author_scope,
      candidates.author_kind,
      candidates.author_key,
      (array_agg(
        candidates.author_name
        order by candidates.document_date desc, candidates.raw_record_id desc
      ))[1] as author_name,
      (array_agg(
        candidates.author_code
        order by candidates.document_date desc, candidates.raw_record_id desc
      ))[1] as author_code,
      case
        when candidates.author_scope = 'person'
          and count(candidates.representative_profile_url) = count(*)
          and count(distinct candidates.representative_profile_url) = 1
        then max(candidates.representative_source_kind)
      end as representative_source_kind,
      case
        when candidates.author_scope = 'person'
          and count(candidates.representative_profile_url) = count(*)
          and count(distinct candidates.representative_profile_url) = 1
        then max(candidates.representative_external_id)
      end as representative_external_id,
      case
        when candidates.author_scope = 'person'
          and count(candidates.representative_profile_url) = count(*)
          and count(distinct candidates.representative_profile_url) = 1
        then max(candidates.representative_profile_url)
      end as representative_profile_url,
      count(distinct candidates.amendment_code)::integer as amendment_count,
      coalesce(sum(candidates.committed_amount) filter (
        where candidates.expense_stage = 'commitment'
      ), 0)::numeric(20,2) as committed_amount,
      coalesce(sum(candidates.paid_amount) filter (
        where candidates.expense_stage = 'payment'
      ), 0)::numeric(20,2) as effective_paid_amount,
      min(candidates.amendment_year)::smallint as first_year,
      max(candidates.amendment_year)::smallint as last_year
    from candidates
    group by
      candidates.legislature_number,
      candidates.legislature_label,
      candidates.full_fiscal_year_from,
      candidates.full_fiscal_year_to,
      candidates.author_scope,
      candidates.author_kind,
      candidates.author_key
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
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    case
      when ranked.representative_profile_url is not null
        then 'approved_official_author_code_crosswalk'
      else 'not_linked'
    end,
    ranked.amendment_count,
    ranked.committed_amount,
    ranked.effective_paid_amount,
    ranked.first_year,
    ranked.last_year,
    'committed'::text,
    'cgu-federal-amendment-legislature-ranking/2.0.0'::text
  from ranked
  where ranked.rank_position <= page_size_per_legislature
  order by
    ranked.legislature_number desc,
    ranked.author_scope,
    ranked.rank_position;
end;
$$;

revoke all on function
  api.get_public_cgu_federal_amendment_legislature_ranking(integer)
  from public;

grant execute on function
  api.get_public_cgu_federal_amendment_legislature_ranking(integer)
  to anon, authenticated;

comment on function
  api.get_public_cgu_federal_amendment_legislature_ranking(integer) is
  'Ranking CGU documental por ano da emenda e legislatura; empenhos e pagamentos separados, sem soma com o agregado ou Transferegov; perfis apenas por crosswalk oficial aprovado.';

notify pgrst, 'reload schema';

commit;
