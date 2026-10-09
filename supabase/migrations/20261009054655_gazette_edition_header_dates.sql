begin;

-- gazette-edition-header-date/1.0.0. As edições do Diário obtidas direto do
-- PDF oficial não trazem data nos metadados quando o catálogo da plataforma
-- nova não as cobre (todo o backfill de 2021-2022 e parte de 2023-2024: 662
-- edições sem data em 09/10/2026). A data está impressa no cabeçalho de cada
-- página ("Barreiras-Bahia - Edição 3460 - 17 de Junho de 2021 - ANO 15"),
-- que no PDF é imagem e só aparece no texto das páginas com OCR.
--
-- Regra determinística: procurar o cabeçalho em todas as páginas com texto
-- da edição; aceitar só ocorrências cujo número de edição é o do PDF, com
-- data válida no ano da pasta oficial; a data é registrada quando todas as
-- ocorrências concordam ("derived"), com a página e o trecho literal como
-- evidência. Sem ocorrência: "not_found"; datas divergentes: "ambiguous".
-- Nenhuma data é inferida de edições vizinhas. Uma edição "derived" não é
-- reavaliada; as demais são reavaliadas quando ganham páginas com texto.
create table editorial.gazette_edition_header_dates (
  raw_artifact_id uuid primary key references raw.raw_artifacts(id),
  edition integer not null check (edition > 0),
  edition_year integer not null check (edition_year between 2000 and 2100),
  status text not null check (status in ('derived', 'not_found', 'ambiguous')),
  edition_date date,
  evidence_page_id uuid references raw.document_pages(id),
  evidence_excerpt text,
  matching_pages integer not null check (matching_pages >= 0),
  pages_checked integer not null check (pages_checked >= 0),
  rule_version text not null,
  checked_at timestamptz not null,
  check (
    (status = 'derived') = (
      edition_date is not null
      and evidence_page_id is not null
      and evidence_excerpt is not null
    )
  ),
  check (edition_date is null or extract(year from edition_date)::integer = edition_year)
);

create index gazette_edition_header_dates_evidence_page_idx
  on editorial.gazette_edition_header_dates (evidence_page_id);

alter table editorial.gazette_edition_header_dates enable row level security;
alter table editorial.gazette_edition_header_dates force row level security;
revoke all on editorial.gazette_edition_header_dates from public, anon, authenticated;

comment on table editorial.gazette_edition_header_dates is
  'Data da edição lida do cabeçalho impresso no PDF oficial (gazette-edition-header-date/1.0.0), com página e trecho como evidência; usada só quando a versão do documento não tem data.';

create function editorial.derive_gazette_edition_header_dates(p_limit integer default 20)
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  processed integer;
begin
  if p_limit < 1 or p_limit > 200 then
    raise exception 'p_limit deve estar entre 1 e 200' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(hashtext('editorial.gazette_edition_header_dates'));

  with candidates as (
    select
      artifact.id,
      (artifact.metadata ->> 'edition')::integer as edition,
      (artifact.metadata ->> 'year')::integer as edition_year,
      pages.pages_with_text
    from raw.raw_artifacts as artifact
    cross join lateral (
      select count(*)::integer as pages_with_text
      from raw.document_pages as page
      where page.raw_artifact_id = artifact.id
        and page.text_content is not null
        and octet_length(page.text_content) > 64
    ) as pages
    left join editorial.gazette_edition_header_dates as previous
      on previous.raw_artifact_id = artifact.id
    where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
      and coalesce(artifact.metadata ->> 'edition', '') ~ '^[0-9]+$'
      and coalesce(artifact.metadata ->> 'year', '') ~ '^[0-9]{4}$'
      and artifact.metadata ->> 'date' is null
      and artifact.metadata ->> 'edition_date' is null
      and pages.pages_with_text > 0
      and (
        previous.raw_artifact_id is null
        or (previous.status <> 'derived'
          and previous.pages_checked < pages.pages_with_text)
      )
    order by (artifact.metadata ->> 'year')::integer desc,
      (artifact.metadata ->> 'edition')::integer desc
    limit p_limit
  ), matches as (
    select
      candidate.id,
      page.id as page_id,
      page.page_number,
      match.groups
    from candidates as candidate
    join raw.document_pages as page
      on page.raw_artifact_id = candidate.id
     and page.text_content is not null
     and octet_length(page.text_content) > 64
    cross join lateral regexp_matches(
      regexp_replace(page.text_content, '\s+', ' ', 'g'),
      'Edi[çcÇC][ãaÃA]o\s*(?:n\s*[º°o.]*\s*)?([0-9]{3,5})\s*[-–—]\s*([0-9]{1,2})\s*de\s*([A-Za-zçÇ]+)\s*de\s*([0-9]{4})',
      'gi'
    ) as match(groups)
  ), parsed as (
    select
      matches.id, matches.page_id, matches.page_number,
      matches.groups[1]::integer as header_edition,
      matches.groups[2]::integer as day_number,
      case translate(lower(matches.groups[3]), 'ç', 'c')
        when 'janeiro' then 1 when 'fevereiro' then 2 when 'marco' then 3
        when 'abril' then 4 when 'maio' then 5 when 'junho' then 6
        when 'julho' then 7 when 'agosto' then 8 when 'setembro' then 9
        when 'outubro' then 10 when 'novembro' then 11 when 'dezembro' then 12
      end as month_number,
      matches.groups[4]::integer as year_number,
      'Edição ' || matches.groups[1] || ' - ' || matches.groups[2] || ' de '
        || matches.groups[3] || ' de ' || matches.groups[4] as excerpt
    from matches
  ), valid as (
    select
      parsed.*,
      make_date(parsed.year_number, parsed.month_number, parsed.day_number) as header_date
    from parsed
    join candidates as candidate on candidate.id = parsed.id
    where parsed.header_edition = candidate.edition
      and parsed.year_number = candidate.edition_year
      and parsed.month_number is not null
      and parsed.day_number between 1 and 31
      and parsed.day_number <= extract(day from (
        make_date(parsed.year_number, parsed.month_number, 1)
          + interval '1 month - 1 day'
      ))
  ), summary as (
    select
      candidate.id,
      candidate.edition,
      candidate.edition_year,
      candidate.pages_with_text,
      count(distinct valid.page_id)::integer as matching_pages,
      count(distinct valid.header_date)::integer as distinct_dates,
      min(valid.header_date) as header_date
    from candidates as candidate
    left join valid on valid.id = candidate.id
    group by candidate.id, candidate.edition, candidate.edition_year,
      candidate.pages_with_text
  ), evidence as (
    select distinct on (valid.id)
      valid.id, valid.page_id, valid.excerpt
    from valid
    order by valid.id, valid.page_number, valid.page_id
  ), upserted as (
    insert into editorial.gazette_edition_header_dates (
      raw_artifact_id, edition, edition_year, status, edition_date,
      evidence_page_id, evidence_excerpt, matching_pages, pages_checked,
      rule_version, checked_at
    )
    select
      summary.id,
      summary.edition,
      summary.edition_year,
      case
        when summary.distinct_dates = 1 then 'derived'
        when summary.distinct_dates > 1 then 'ambiguous'
        else 'not_found'
      end,
      case when summary.distinct_dates = 1 then summary.header_date end,
      case when summary.distinct_dates = 1 then evidence.page_id end,
      case when summary.distinct_dates = 1 then evidence.excerpt end,
      summary.matching_pages,
      summary.pages_with_text,
      'gazette-edition-header-date/1.0.0',
      statement_timestamp()
    from summary
    left join evidence on evidence.id = summary.id
    on conflict (raw_artifact_id) do update
    set
      status = excluded.status,
      edition_date = excluded.edition_date,
      evidence_page_id = excluded.evidence_page_id,
      evidence_excerpt = excluded.evidence_excerpt,
      matching_pages = excluded.matching_pages,
      pages_checked = excluded.pages_checked,
      rule_version = excluded.rule_version,
      checked_at = excluded.checked_at
    where editorial.gazette_edition_header_dates.status <> 'derived'
    returning 1
  )
  select count(*)::integer into processed from upserted;
  return processed;
end;
$function$;

revoke all on function editorial.derive_gazette_edition_header_dates(integer)
  from public, anon, authenticated;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-gazette-edition-header-dates', '7,27,47 * * * *',
      'select editorial.derive_gazette_edition_header_dates(40)');
  end if;
end;
$schedule$;

commit;
