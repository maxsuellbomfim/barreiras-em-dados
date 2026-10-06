begin;

-- camara-legislative-latest/1.0.0: a página da Câmara deduplicava, a cada
-- visita, ~50 mil registros brutos (cada coleta reinsere os itens) para obter
-- ~7,6 mil leis e indicações distintas; o resumo por vereador passou de 9 s e
-- o gráfico sumia do site (o cliente desiste em 5 s). A versão mais recente de
-- cada item passa a viver numa tabela compacta, mantida por gatilho na chegada
-- do bruto. O bruto continua append-only; cada linha aponta o raw_record de
-- origem. As regras de leitura (campos, filtros e "mais recente por item")
-- são as mesmas das funções anteriores.

create table political.camara_legislative_items (
  item_kind text not null check (item_kind in ('lei', 'indicacao')),
  item_id text not null check (length(item_id) between 1 and 64),
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
  collected_at timestamptz not null,
  raw_record_id uuid not null references raw.raw_records(id),
  author_norm text generated always as (api.normalize_public_author_name(author_name)) stored,
  author_key text generated always as (political.council_author_key_v1(author_name)) stored,
  primary key (item_kind, item_id)
);

create index camara_legislative_items_raw_record_idx
  on political.camara_legislative_items (raw_record_id);
create index camara_legislative_items_author_norm_idx
  on political.camara_legislative_items (author_norm);
create index camara_legislative_items_author_key_idx
  on political.camara_legislative_items (author_key);

alter table political.camara_legislative_items enable row level security;
revoke all on political.camara_legislative_items from public, anon, authenticated;

-- Mesmas expressões das funções públicas anteriores (lei e indicação).
create function political.camara_legislative_item_from_raw(
  p_record_type text,
  p_payload jsonb
)
returns table (
  item_kind text,
  item_id text,
  protocol_number text,
  publication_date text,
  reference_year integer,
  item_type text,
  title text,
  summary text,
  author_name text,
  situation text,
  source_url text,
  active boolean
)
language sql
immutable
set search_path = ''
as $function$
  select
    'lei',
    btrim(p_payload ->> 'id_lei'),
    null::text,
    case when p_payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and p_payload ->> 'data' <> '0000-00-00' then p_payload ->> 'data' end,
    case when p_payload ->> 'ano_ref' ~ '^[0-9]{4}$' then (p_payload ->> 'ano_ref')::integer
      when p_payload ->> 'data' ~ '^[0-9]{4}' then left(p_payload ->> 'data', 4)::integer end,
    nullif(btrim(p_payload ->> 'tipo'), ''),
    nullif(btrim(p_payload ->> 'titulo'), ''),
    nullif(btrim(p_payload ->> 'informacoes'), ''),
    nullif(btrim(coalesce(p_payload ->> 'autoria', p_payload ->> 'autor', p_payload ->> 'author')), ''),
    null::text,
    case when p_payload ->> 'url' ~ '^https://' then p_payload ->> 'url'
      when p_payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(p_payload ->> 'url', '/') end,
    case when lower(p_payload ->> 'ativo') in ('true', '1', 'sim') then true
      when lower(p_payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end
  where p_record_type = 'municipal_transparency_leis'
    and length(btrim(p_payload ->> 'id_lei')) > 0
    and (length(btrim(p_payload ->> 'titulo')) > 0 or length(btrim(p_payload ->> 'informacoes')) > 0)
  union all
  select
    'indicacao',
    btrim(p_payload ->> 'id_indicacao'),
    nullif(btrim(p_payload ->> 'numero_protocolo'), ''),
    case when p_payload ->> 'data_protocolo' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and p_payload ->> 'data_protocolo' <> '0000-00-00' then p_payload ->> 'data_protocolo'
      when p_payload ->> 'data_aprovacao' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and p_payload ->> 'data_aprovacao' <> '0000-00-00' then p_payload ->> 'data_aprovacao'
      when p_payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and p_payload ->> 'data' <> '0000-00-00' then p_payload ->> 'data' end,
    case when p_payload ->> 'data_protocolo' ~ '^[0-9]{4}' then left(p_payload ->> 'data_protocolo', 4)::integer
      when p_payload ->> 'data_aprovacao' ~ '^[0-9]{4}' then left(p_payload ->> 'data_aprovacao', 4)::integer end,
    nullif(btrim(p_payload ->> 'tipo'), ''),
    nullif(btrim(p_payload ->> 'titulo'), ''),
    nullif(btrim(p_payload ->> 'informacoes'), ''),
    nullif(btrim(coalesce(p_payload ->> 'autoria', p_payload ->> 'autor')), ''),
    nullif(btrim(p_payload ->> 'situacao'), ''),
    case when p_payload ->> 'url' ~ '^https://' then p_payload ->> 'url'
      when p_payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(p_payload ->> 'url', '/') end,
    case when lower(p_payload ->> 'ativo') in ('true', '1', 'sim') then true
      when lower(p_payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end
  where p_record_type = 'municipal_transparency_indicacoes'
    and length(btrim(p_payload ->> 'id_indicacao')) > 0
    and length(btrim(p_payload ->> 'informacoes')) > 0
$function$;

create function political.track_camara_legislative_item()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  insert into political.camara_legislative_items (
    item_kind, item_id, protocol_number, publication_date, reference_year, item_type,
    title, summary, author_name, situation, source_url, active, collected_at, raw_record_id
  )
  select item.*, new.collected_at, new.id
  from political.camara_legislative_item_from_raw(new.record_type, new.payload) as item
  on conflict (item_kind, item_id) do update
  set
    protocol_number = excluded.protocol_number,
    publication_date = excluded.publication_date,
    reference_year = excluded.reference_year,
    item_type = excluded.item_type,
    title = excluded.title,
    summary = excluded.summary,
    author_name = excluded.author_name,
    situation = excluded.situation,
    source_url = excluded.source_url,
    active = excluded.active,
    collected_at = excluded.collected_at,
    raw_record_id = excluded.raw_record_id
  where excluded.collected_at >= political.camara_legislative_items.collected_at;
  return null;
end;
$function$;

create trigger raw_records_track_camara_legislative_item
after insert on raw.raw_records
for each row
when (new.record_type in ('municipal_transparency_leis', 'municipal_transparency_indicacoes'))
execute function political.track_camara_legislative_item();

-- Carga inicial: a versão mais recente de cada item no acervo já coletado.
insert into political.camara_legislative_items (
  item_kind, item_id, protocol_number, publication_date, reference_year, item_type,
  title, summary, author_name, situation, source_url, active, collected_at, raw_record_id
)
select distinct on (item.item_kind, item.item_id)
  item.*, record.collected_at, record.id
from raw.raw_records as record
cross join lateral political.camara_legislative_item_from_raw(record.record_type, record.payload) as item
where record.record_type in ('municipal_transparency_leis', 'municipal_transparency_indicacoes')
order by item.item_kind, item.item_id, record.collected_at desc, record.id desc;

-- Elenco atual e aliases aprovados (mesma regra das funções anteriores).
create function political.camara_current_author_names()
returns table (canonical_name text, canonical_key text, name_key text)
language sql
stable
security definer
set search_path = ''
as $function$
  with current_roster as (
    select distinct on (record.source_record_key)
      record.source_record_key,
      nullif(btrim(record.payload ->> 'nome'), '') as canonical_name
    from raw.raw_records as record
    where record.record_type = 'cm_barreiras_vereador'
      and nullif(btrim(record.payload ->> 'nome'), '') is not null
    order by record.source_record_key, record.collected_at desc
  )
  select roster.canonical_name,
    api.normalize_public_author_name(roster.canonical_name),
    api.normalize_public_author_name(roster.canonical_name)
  from current_roster as roster
  union all
  select roster.canonical_name,
    api.normalize_public_author_name(roster.canonical_name),
    api.normalize_public_author_name(alias_row.alias_text)
  from current_roster as roster
  join political.representative_aliases as alias_row
    on alias_row.source_kind = 'municipal'
   and alias_row.representative_external_id = roster.source_record_key
   and alias_row.active
   and nullif(btrim(alias_row.alias_text), '') is not null
$function$;

revoke all on function political.camara_current_author_names() from public, anon, authenticated;

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
  with current_names as materialized (
    select * from political.camara_current_author_names()
  ), filter_names as materialized (
    -- Nomes equivalentes ao filtro: o próprio, os aliases do mesmo vereador
    -- atual e (council-former-authors/1.0.0) a chave do vínculo com o TSE.
    select candidate_name.name_key
    from current_names as filter_name
    join current_names as candidate_name
      on candidate_name.canonical_key = filter_name.canonical_key
    where filter_name.name_key = api.normalize_public_author_name(author_filter)
  ), filtered as (
    select item.*
    from political.camara_legislative_items as item
    where (item_kind_filter is null or item.item_kind = item_kind_filter)
      and (year_filter is null or item.reference_year = year_filter)
      and (
        author_filter is null
        or item.author_norm = api.normalize_public_author_name(author_filter)
        or item.author_key = political.council_author_key_v1(author_filter)
        or item.author_norm in (select name_key from filter_names)
      )
      and (query_filter is null or lower(concat_ws(' ', item.item_id, item.protocol_number, item.title, item.summary, item.author_name)) like '%' || lower(btrim(query_filter)) || '%')
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

create or replace function api.get_camara_current_author_summary(
  item_kind_filter text default null,
  year_filter integer default null,
  author_filter text default null,
  query_filter text default null
)
returns table (author_name text, item_count bigint)
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
  with current_names as materialized (
    select * from political.camara_current_author_names()
  ), resolved as (
    select item.*,
      (select min(current_name.canonical_name)
       from current_names as current_name
       where current_name.name_key = item.author_norm) as current_author_name
    from political.camara_legislative_items as item
    where (item_kind_filter is null or item.item_kind = item_kind_filter)
      and (year_filter is null or item.reference_year = year_filter)
      and (query_filter is null or lower(concat_ws(' ', item.item_id, item.title, item.summary, item.author_name)) like '%' || lower(btrim(query_filter)) || '%')
  ), filtered as (
    select resolved.*
    from resolved
    where resolved.current_author_name is not null
      and (
        author_filter is null
        or resolved.author_norm = api.normalize_public_author_name(author_filter)
        or api.normalize_public_author_name(resolved.current_author_name) = api.normalize_public_author_name(author_filter)
        or exists (
          select 1 from current_names as filter_name
          where filter_name.name_key = api.normalize_public_author_name(author_filter)
            and filter_name.canonical_name = resolved.current_author_name
        )
      )
  )
  select filtered.current_author_name, count(*)::bigint
  from filtered
  group by filtered.current_author_name
  order by count(*) desc, filtered.current_author_name;
end;
$function$;

-- Vereadores de legislaturas encerradas; os da legislatura em curso ficam no
-- resumo atual e suas grafias variantes, na fila de aliases.
create or replace function api.get_camara_former_author_summary(
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
declare
  current_year integer := extract(year from statement_timestamp() at time zone 'America/Bahia')::integer;
begin
  if item_kind_filter is not null and item_kind_filter not in ('lei', 'indicacao') then
    raise exception 'item_kind_filter deve ser lei ou indicacao' using errcode = '22023';
  end if;
  if year_filter is not null and (year_filter < 1900 or year_filter > 2200) then
    raise exception 'year_filter fora do intervalo' using errcode = '22023';
  end if;

  return query
  with current_names as materialized (
    select name_key from political.camara_current_author_names()
  ), mandates as materialized (
    select * from political.tse_council_mandates_v1() as mandate
    where mandate.term_end_year < current_year
  ), filtered as (
    select item.*
    from political.camara_legislative_items as item
    where item.author_name is not null
      and item.reference_year is not null
      and item.author_norm not in (select name_key from current_names)
      and (item_kind_filter is null or item.item_kind = item_kind_filter)
      and (year_filter is null or item.reference_year = year_filter)
      and (query_filter is null or lower(concat_ws(' ', item.item_id, item.title, item.summary, item.author_name)) like '%' || lower(btrim(query_filter)) || '%')
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

commit;
