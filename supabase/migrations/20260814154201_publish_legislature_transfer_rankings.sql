begin;

create table political.legislative_terms (
  sphere text not null check (sphere in ('federal', 'state')),
  legislature_number smallint not null check (legislature_number > 0),
  legislature_label text not null
    check (length(btrim(legislature_label)) between 10 and 200),
  begins_on date not null,
  ends_on date not null,
  full_fiscal_year_from smallint not null,
  full_fiscal_year_to smallint not null,
  excluded_transition_years smallint[] not null default '{}',
  official_source_url text not null check (official_source_url ~ '^https://'),
  official_source_note text not null
    check (length(btrim(official_source_note)) between 20 and 1000),
  methodology_version text not null
    default 'legislative-terms/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  primary key (sphere, legislature_number),
  check (begins_on < ends_on),
  check (full_fiscal_year_from <= full_fiscal_year_to),
  check (full_fiscal_year_from >= extract(year from begins_on)::smallint),
  check (full_fiscal_year_to <= extract(year from ends_on)::smallint),
  check (cardinality(excluded_transition_years) <= 4)
);

create trigger legislative_terms_set_updated_at
before update on political.legislative_terms
for each row execute function audit.set_updated_at();

alter table political.legislative_terms enable row level security;
alter table political.legislative_terms force row level security;
revoke all on table political.legislative_terms
  from public, anon, authenticated;

insert into political.legislative_terms (
  sphere,
  legislature_number,
  legislature_label,
  begins_on,
  ends_on,
  full_fiscal_year_from,
  full_fiscal_year_to,
  excluded_transition_years,
  official_source_url,
  official_source_note
)
values
  (
    'federal', 56, '56ª Legislatura da Câmara dos Deputados',
    '2019-02-01', '2023-01-31', 2020, 2022, array[2023]::smallint[],
    'https://www2.camara.leg.br/transparencia/prestacao-de-contas/contas-da-camara/ano-de-2019/informativo-para-a-sociedade-2019',
    'A Câmara informa que a 56ª Legislatura se estendeu de 2019 a 2023.'
  ),
  (
    'federal', 57, '57ª Legislatura da Câmara dos Deputados',
    '2023-02-01', '2027-01-31', 2024, 2026, array[2023]::smallint[],
    'https://www2.camara.leg.br/atividade-legislativa/comissoes/grupos-de-trabalho/57a-legislatura/',
    'A Câmara organiza a atividade legislativa corrente sob a 57ª Legislatura.'
  ),
  (
    'state', 19, '19ª Legislatura da Assembleia Legislativa da Bahia',
    '2019-02-01', '2023-01-31', 2020, 2022, array[2023]::smallint[],
    'https://www.al.ba.gov.br/midia-center/noticias/32631',
    'A ALBA registra a posse dos parlamentares da 19ª Legislatura em fevereiro de 2019.'
  ),
  (
    'state', 20, '20ª Legislatura da Assembleia Legislativa da Bahia',
    '2023-02-01', '2027-01-31', 2024, 2026, array[2023]::smallint[],
    'https://www.al.ba.gov.br/midia-center/noticias/55953',
    'A ALBA registra o início da 20ª Legislatura em fevereiro de 2023.'
  );

create function api.get_public_parliamentary_legislature_rankings(
  sphere_filter text default null,
  legislature_number_filter smallint default null,
  page_size_per_legislature integer default 10
)
returns table (
  sphere text,
  legislature_number smallint,
  legislature_label text,
  begins_on date,
  ends_on date,
  full_fiscal_year_from smallint,
  full_fiscal_year_to smallint,
  official_source_url text,
  official_source_note text,
  excluded_transition_years smallint[],
  ranking_amount_stage text,
  rank_position integer,
  author_key text,
  author_name text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  amendment_count integer,
  ranking_amount numeric(20,2),
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if sphere_filter is not null and sphere_filter not in ('federal', 'state') then
    raise exception 'esfera legislativa deve ser federal ou state'
      using errcode = '22023';
  end if;
  if legislature_number_filter is not null and legislature_number_filter < 1 then
    raise exception 'numero de legislatura invalido'
      using errcode = '22023';
  end if;
  if page_size_per_legislature is null
    or page_size_per_legislature < 1
    or page_size_per_legislature > 10
  then
    raise exception 'limite por legislatura deve estar entre 1 e 10'
      using errcode = '22023';
  end if;

  return query
  with selected_terms as (
    select term.*
    from political.legislative_terms as term
    where (sphere_filter is null or term.sphere = sphere_filter)
      and (
        legislature_number_filter is null
        or term.legislature_number = legislature_number_filter
      )
  ), federal_grouped as (
    select
      term.sphere,
      term.legislature_number,
      transfer.author_key,
      max(transfer.author_name) as author_name,
      count(*)::integer as amendment_count,
      sum(transfer.destination_amount)::numeric(20,2) as ranking_amount,
      sum(transfer.committed_amount)::numeric(20,2) as committed_amount,
      null::numeric(20,2) as liquidated_amount,
      sum(transfer.paid_amount)::numeric(20,2) as paid_amount,
      min(transfer.fiscal_year)::smallint as first_year,
      max(transfer.fiscal_year)::smallint as last_year
    from selected_terms as term
    join territory.reconciled_parliamentary_transfers as transfer
      on term.sphere = 'federal'
     and transfer.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
    where transfer.author_kind = 'person'
      and transfer.reconciliation_status not like 'conflict_%'
      and transfer.destination_amount is not null
    group by term.sphere, term.legislature_number, transfer.author_key
  ), state_grouped as (
    select
      term.sphere,
      term.legislature_number,
      amendment.author_key,
      (array_agg(
        amendment.author_name
        order by amendment.fiscal_year desc, amendment.amendment_number
      ))[1] as author_name,
      count(*)::integer as amendment_count,
      sum(amendment.authorized_amount)::numeric(20,2) as ranking_amount,
      sum(amendment.committed_amount) filter (
        where amendment.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as committed_amount,
      sum(amendment.liquidated_amount) filter (
        where amendment.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as liquidated_amount,
      sum(amendment.paid_amount) filter (
        where amendment.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as paid_amount,
      min(amendment.fiscal_year)::smallint as first_year,
      max(amendment.fiscal_year)::smallint as last_year
    from selected_terms as term
    join territory.bahia_state_loa_execution_reconciliation_snapshot as amendment
      on term.sphere = 'state'
     and amendment.fiscal_year between
       term.full_fiscal_year_from and term.full_fiscal_year_to
    group by term.sphere, term.legislature_number, amendment.author_key
  ), grouped as (
    select * from federal_grouped
    union all
    select * from state_grouped
  ), linked as (
    select
      grouped.*,
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      case
        when crosswalk.author_key is not null
          then 'approved_official_crosswalk'
        else 'not_linked'
      end as association_status
    from grouped
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
     and crosswalk.author_key = grouped.author_key
     and crosswalk.review_status = 'approved'
  ), ranked as (
    select
      linked.*,
      row_number() over (
        partition by linked.sphere, linked.legislature_number
        order by
          linked.ranking_amount desc,
          linked.amendment_count desc,
          linked.author_name,
          linked.author_key
      )::integer as rank_position
    from linked
  )
  select
    term.sphere,
    term.legislature_number,
    term.legislature_label,
    term.begins_on,
    term.ends_on,
    term.full_fiscal_year_from,
    term.full_fiscal_year_to,
    term.official_source_url,
    term.official_source_note,
    term.excluded_transition_years,
    case term.sphere
      when 'federal' then 'destination'
      else 'authorized'
    end as ranking_amount_stage,
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    ranked.association_status,
    ranked.amendment_count,
    ranked.ranking_amount,
    ranked.committed_amount,
    ranked.liquidated_amount,
    ranked.paid_amount,
    ranked.first_year,
    ranked.last_year,
    'parliamentary-legislature-transfer-ranking/1.0.0'::text
  from selected_terms as term
  left join ranked
    on ranked.sphere = term.sphere
   and ranked.legislature_number = term.legislature_number
   and ranked.rank_position <= page_size_per_legislature
  order by
    case term.sphere when 'state' then 0 else 1 end,
    term.legislature_number desc,
    ranked.rank_position nulls last;
end;
$function$;

revoke all on function api.get_public_parliamentary_legislature_rankings(
  text, smallint, integer
) from public;
grant execute on function api.get_public_parliamentary_legislature_rankings(
  text, smallint, integer
) to anon, authenticated;

comment on table political.legislative_terms is
  'Periodos oficiais usados para separar rankings por legislatura; a tabela e privada e versionada por migration.';
comment on function api.get_public_parliamentary_legislature_rankings(
  text, smallint, integer
) is
  'Publica ate dez autorias individuais por legislatura e esfera; ordena por valor destinado federal ou autorizado estadual e separa execucao.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:publish-legislature-transfer-rankings',
  'methodology.legislature_rankings_published',
  'political.legislative_terms',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'parliamentary-legislature-transfer-ranking/1.0.0',
    'term_count', 4,
    'transition_year_excluded', 2023
  ),
  jsonb_build_object(
    'federal_ranking_stage', 'destination',
    'state_ranking_stage', 'authorized',
    'maximum_rows_per_legislature', 10
  )
);

notify pgrst, 'reload schema';

commit;
