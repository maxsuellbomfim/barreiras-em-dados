begin;

-- council-former-authors/1.0.0: autoria de leis e indicações por vereadores de
-- legislaturas anteriores. O mandato vem do acervo oficial do TSE (votação por
-- candidatura em Barreiras, já preservada com hash): vereador ELEITO no pleito
-- de N exerce de N+1 a N+4. Um item é atribuído a esse vereador somente quando
-- a autoria publicada pela Câmara, normalizada, é idêntica ao nome oficial do
-- TSE e o ano do item cai dentro do mandato. Grafias diferentes, apelidos e
-- suplentes em exercício continuam sem vínculo (revisão humana).

-- Chave de comparação: sem acento, caixa, pontuação, conteúdo entre parênteses
-- e prefixos de tratamento; "JR" vira "JUNIOR". Não abrevia nem completa nomes.
create function political.council_author_key_v1(value text)
returns text
language sql
immutable
strict
parallel safe
set search_path = ''
as $function$
  select regexp_replace(
    regexp_replace(
      btrim(regexp_replace(regexp_replace(regexp_replace(
        translate(upper(value),
          'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC'),
        '\([^)]*\)', ' ', 'g'),
        '[.,;:''-]', ' ', 'g'),
        '\s+', ' ', 'g')),
      '^((VEREADORA|VEREADOR|DRA|DR) )+', ''),
    '\mJR\M', 'JUNIOR', 'g')
$function$;

-- Mandatos de vereador em Barreiras pelo TSE (somente eleitos).
create function political.tse_council_mandates_v1()
returns table (
  election_year integer,
  canonical_name text,
  ballot_name text,
  party text,
  outcome text,
  term_start_year integer,
  term_end_year integer,
  author_key text,
  source_record_key text,
  source_url text,
  artifact_sha256 text
)
language sql
stable
security definer
set search_path = ''
as $function$
  select
    latest.election_year,
    latest.canonical_name,
    latest.ballot_name,
    latest.party,
    latest.outcome,
    latest.election_year + 1,
    latest.election_year + 4,
    political.council_author_key_v1(latest.canonical_name),
    latest.source_record_key,
    latest.source_url,
    latest.sha256
  from (
    select distinct on (record.source_record_key)
      (record.payload ->> 'ano')::integer as election_year,
      btrim(record.payload ->> 'nome') as canonical_name,
      nullif(btrim(record.payload ->> 'nome_urna'), '') as ballot_name,
      nullif(btrim(record.payload ->> 'partido'), '') as party,
      btrim(record.payload ->> 'situacao') as outcome,
      record.source_record_key,
      artifact.source_url,
      artifact.sha256
    from raw.raw_records as record
    join raw.raw_artifacts as artifact on artifact.id = record.raw_artifact_id
    where record.record_type = 'tse_votacao_barreiras'
      and lower(record.payload ->> 'cargo') = 'vereador'
      and upper(record.payload ->> 'situacao') like 'ELEITO%'
      and record.payload ->> 'ano' ~ '^20[0-9]{2}$'
      and length(btrim(record.payload ->> 'nome')) > 0
    order by record.source_record_key, record.collected_at desc
  ) as latest
  -- Pleitos municipais (2012, 2016, 2020, 2024...).
  where latest.election_year % 4 = 0
$function$;

revoke all on function political.tse_council_mandates_v1() from public, anon, authenticated;

create function api.get_camara_former_author_summary(
  item_kind_filter text default null,
  year_filter integer default null,
  query_filter text default null
)
returns table (
  author_name text,
  elected_terms text,
  item_count bigint,
  source_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if item_kind_filter is not null and item_kind_filter not in ('lei', 'indicacao') then
    raise exception 'item_kind_filter deve ser lei ou indicacao' using errcode = '22023';
  end if;
  if year_filter is not null and (year_filter < 1900 or year_filter > 2200) then
    raise exception 'year_filter fora do intervalo' using errcode = '22023';
  end if;

  return query
  with current_roster as (
    select distinct on (record.source_record_key)
      record.source_record_key,
      nullif(btrim(record.payload ->> 'nome'), '') as canonical_name
    from raw.raw_records as record
    where record.record_type = 'cm_barreiras_vereador'
      and nullif(btrim(record.payload ->> 'nome'), '') is not null
    order by record.source_record_key, record.collected_at desc
  ), current_names as (
    select api.normalize_public_author_name(roster.canonical_name) as name_key
    from current_roster as roster
    union
    select api.normalize_public_author_name(alias_row.alias_text)
    from current_roster as roster
    join political.representative_aliases as alias_row
      on alias_row.source_kind = 'municipal'
     and alias_row.representative_external_id = roster.source_record_key
     and alias_row.active
     and nullif(btrim(alias_row.alias_text), '') is not null
  ), mandates as materialized (
    select * from political.tse_council_mandates_v1()
  ), candidates as (
    select btrim(record.payload ->> 'id_lei') as item_id, 'lei'::text as item_kind,
      case when record.payload ->> 'ano_ref' ~ '^[0-9]{4}$' then (record.payload ->> 'ano_ref')::integer
        when record.payload ->> 'data' ~ '^[0-9]{4}' then left(record.payload ->> 'data', 4)::integer end as reference_year,
      nullif(btrim(record.payload ->> 'titulo'), '') as title,
      nullif(btrim(record.payload ->> 'informacoes'), '') as summary,
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor', record.payload ->> 'author')), '') as author_name,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_leis'
      and length(btrim(record.payload ->> 'id_lei')) > 0
      and (length(btrim(record.payload ->> 'titulo')) > 0 or length(btrim(record.payload ->> 'informacoes')) > 0)
    union all
    select btrim(record.payload ->> 'id_indicacao'), 'indicacao'::text,
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}' then left(record.payload ->> 'data_protocolo', 4)::integer
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}' then left(record.payload ->> 'data_aprovacao', 4)::integer end,
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor')), ''),
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_indicacoes'
      and length(btrim(record.payload ->> 'id_indicacao')) > 0
      and length(btrim(record.payload ->> 'informacoes')) > 0
  ), latest as (
    select distinct on (candidates.item_kind, candidates.item_id) candidates.*
    from candidates
    order by candidates.item_kind, candidates.item_id, candidates.collected_at desc
  ), filtered as (
    select latest.*, political.council_author_key_v1(latest.author_name) as author_key
    from latest
    where latest.author_name is not null
      and latest.reference_year is not null
      and api.normalize_public_author_name(latest.author_name) not in (select name_key from current_names)
      and (item_kind_filter is null or latest.item_kind = item_kind_filter)
      and (year_filter is null or latest.reference_year = year_filter)
      and (query_filter is null or lower(concat_ws(' ', latest.item_id, latest.title, latest.summary, latest.author_name)) like '%' || lower(btrim(query_filter)) || '%')
  ), linked as (
    -- Vínculo só quando um único nome oficial do TSE cobre o ano do item.
    select filtered.item_kind, filtered.item_id, min(mandate.canonical_name) as canonical_name
    from filtered
    join mandates as mandate
      on mandate.author_key = filtered.author_key
     and filtered.reference_year between mandate.term_start_year and mandate.term_end_year
    group by filtered.item_kind, filtered.item_id
    having count(distinct mandate.canonical_name) = 1
  ), terms as (
    select mandate.canonical_name,
      string_agg(distinct mandate.term_start_year || '–' || mandate.term_end_year, ', ') as elected_terms,
      min(mandate.source_url) as source_url
    from mandates as mandate
    group by mandate.canonical_name
  )
  select linked.canonical_name, terms.elected_terms, count(*)::bigint,
    terms.source_url, 'council-former-authors/1.0.0'::text
  from linked
  join terms on terms.canonical_name = linked.canonical_name
  group by linked.canonical_name, terms.elected_terms, terms.source_url
  order by count(*) desc, linked.canonical_name;
end;
$function$;

revoke all on function api.get_camara_former_author_summary(text, integer, text) from public;
grant execute on function api.get_camara_former_author_summary(text, integer, text) to anon, authenticated;

-- O clique no nome filtra a lista com a mesma chave usada no vínculo.
create or replace function api.get_camara_legislative_page(
  page_size integer default 50,
  page_offset integer default 0,
  item_kind_filter text default null,
  year_filter integer default null,
  author_filter text default null,
  query_filter text default null
)
returns table (
  total_count bigint,
  item_id text,
  item_kind text,
  protocol_number text,
  publication_date text,
  reference_year integer,
  item_type text,
  title text,
  summary text,
  author_name text,
  situation text,
  source_url text,
  active boolean,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset fora do intervalo' using errcode = '22023';
  end if;
  if item_kind_filter is not null and item_kind_filter not in ('lei', 'indicacao') then
    raise exception 'item_kind_filter deve ser lei ou indicacao' using errcode = '22023';
  end if;
  if year_filter is not null and (year_filter < 1900 or year_filter > 2200) then
    raise exception 'year_filter fora do intervalo' using errcode = '22023';
  end if;

  return query
  with current_roster as (
    select distinct on (record.source_record_key)
      record.source_record_key,
      nullif(btrim(record.payload ->> 'nome'), '') as canonical_name
    from raw.raw_records as record
    where record.record_type = 'cm_barreiras_vereador'
      and nullif(btrim(record.payload ->> 'nome'), '') is not null
    order by record.source_record_key, record.collected_at desc
  ), current_names as (
    select
      roster.canonical_name,
      api.normalize_public_author_name(roster.canonical_name) as canonical_key,
      api.normalize_public_author_name(roster.canonical_name) as name_key
    from current_roster as roster
    union all
    select
      roster.canonical_name,
      api.normalize_public_author_name(roster.canonical_name),
      api.normalize_public_author_name(alias_row.alias_text)
    from current_roster as roster
    join political.representative_aliases as alias_row
      on alias_row.source_kind = 'municipal'
     and alias_row.representative_external_id = roster.source_record_key
     and alias_row.active
     and nullif(btrim(alias_row.alias_text), '') is not null
  ), candidates as (
    select
      btrim(record.payload ->> 'id_lei') as item_id,
      'lei'::text as item_kind,
      null::text as protocol_number,
      case when record.payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        and record.payload ->> 'data' <> '0000-00-00' then record.payload ->> 'data' end as publication_date,
      case when record.payload ->> 'ano_ref' ~ '^[0-9]{4}$' then (record.payload ->> 'ano_ref')::integer
        when record.payload ->> 'data' ~ '^[0-9]{4}' then left(record.payload ->> 'data', 4)::integer end as reference_year,
      nullif(btrim(record.payload ->> 'tipo'), '') as item_type,
      nullif(btrim(record.payload ->> 'titulo'), '') as title,
      nullif(btrim(record.payload ->> 'informacoes'), '') as summary,
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor', record.payload ->> 'author')), '') as author_name,
      null::text as situation,
      case when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/') end as source_url,
      case when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end as active,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_leis'
      and length(btrim(record.payload ->> 'id_lei')) > 0
      and (length(btrim(record.payload ->> 'titulo')) > 0 or length(btrim(record.payload ->> 'informacoes')) > 0)
    union all
    select
      btrim(record.payload ->> 'id_indicacao'),
      'indicacao'::text,
      nullif(btrim(record.payload ->> 'numero_protocolo'), ''),
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_protocolo' <> '0000-00-00' then record.payload ->> 'data_protocolo'
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_aprovacao' <> '0000-00-00' then record.payload ->> 'data_aprovacao'
        when record.payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data' <> '0000-00-00' then record.payload ->> 'data' end,
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}' then left(record.payload ->> 'data_protocolo', 4)::integer
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}' then left(record.payload ->> 'data_aprovacao', 4)::integer end,
      nullif(btrim(record.payload ->> 'tipo'), ''),
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor')), ''),
      nullif(btrim(record.payload ->> 'situacao'), ''),
      case when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/') end,
      case when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_indicacoes'
      and length(btrim(record.payload ->> 'id_indicacao')) > 0
      and length(btrim(record.payload ->> 'informacoes')) > 0
  ), latest as (
    select distinct on (candidates.item_kind, candidates.item_id) candidates.*
    from candidates
    order by candidates.item_kind, candidates.item_id, candidates.collected_at desc
  ), filtered as (
    select latest.*
    from latest
    where (item_kind_filter is null or latest.item_kind = item_kind_filter)
      and (year_filter is null or latest.reference_year = year_filter)
      and (
        author_filter is null
        or api.normalize_public_author_name(latest.author_name) = api.normalize_public_author_name(author_filter)
        -- council-former-authors/1.0.0: mesma chave do vínculo com o TSE.
        or political.council_author_key_v1(latest.author_name) = political.council_author_key_v1(author_filter)
        or exists (
          select 1
          from current_names as filter_name
          join current_names as candidate_name
            on candidate_name.canonical_key = filter_name.canonical_key
           and candidate_name.name_key = api.normalize_public_author_name(latest.author_name)
          where filter_name.name_key = api.normalize_public_author_name(author_filter)
        )
      )
      and (query_filter is null or lower(concat_ws(' ', latest.item_id, latest.protocol_number, latest.title, latest.summary, latest.author_name)) like '%' || lower(btrim(query_filter)) || '%')
  )
  select count(*) over () as total_count, filtered.item_id, filtered.item_kind,
    filtered.protocol_number, filtered.publication_date, filtered.reference_year,
    filtered.item_type, filtered.title, filtered.summary, filtered.author_name,
    filtered.situation, filtered.source_url, filtered.active, filtered.collected_at,
    'camara-legislative/1.0.0'::text
  from filtered
  order by filtered.reference_year desc nulls last, filtered.publication_date desc nulls last,
    filtered.item_kind, filtered.item_id
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.get_camara_legislative_page(integer, integer, text, integer, text, text) from public;
grant execute on function api.get_camara_legislative_page(integer, integer, text, integer, text, text) to anon, authenticated;

commit;
