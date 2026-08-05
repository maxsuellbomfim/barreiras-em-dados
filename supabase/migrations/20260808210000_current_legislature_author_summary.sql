-- Resumo de autoria restrito à legislatura municipal atualmente publicada.
-- O acervo permanece completo; somente o gráfico de representantes em
-- exercício usa esta projeção para não misturar autores históricos.

create or replace function api.get_camara_current_author_summary(
  item_kind_filter text default null,
  year_filter integer default null,
  author_filter text default null,
  query_filter text default null
)
returns table (
  author_name text,
  item_count bigint
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
    select
      roster.canonical_name,
      lower(btrim(regexp_replace(
        regexp_replace(roster.canonical_name, '\\([^)]*\\)', '', 'g'),
        '\\s+', ' ', 'g'
      ))) as name_key
    from current_roster as roster
    union all
    select
      roster.canonical_name,
      lower(btrim(regexp_replace(
        regexp_replace(alias_row.alias_text, '\\([^)]*\\)', '', 'g'),
        '\\s+', ' ', 'g'
      ))) as name_key
    from current_roster as roster
    join political.representative_aliases as alias_row
      on alias_row.source_kind = 'municipal'
     and alias_row.representative_external_id = roster.source_record_key
     and alias_row.active
  ), candidates as (
    select
      btrim(record.payload ->> 'id_lei') as item_id,
      'lei'::text as item_kind,
      case
        when record.payload ->> 'ano_ref' ~ '^[0-9]{4}$'
          then (record.payload ->> 'ano_ref')::integer
        when record.payload ->> 'data' ~ '^[0-9]{4}'
          then left(record.payload ->> 'data', 4)::integer
      end as reference_year,
      nullif(btrim(record.payload ->> 'titulo'), '') as title,
      nullif(btrim(record.payload ->> 'informacoes'), '') as summary,
      nullif(btrim(coalesce(
        record.payload ->> 'autoria',
        record.payload ->> 'autor',
        record.payload ->> 'author'
      )), '') as author_name,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_leis'
      and length(btrim(record.payload ->> 'id_lei')) > 0
      and (
        length(btrim(record.payload ->> 'titulo')) > 0
        or length(btrim(record.payload ->> 'informacoes')) > 0
      )
    union all
    select
      btrim(record.payload ->> 'id_indicacao'),
      'indicacao'::text,
      case
        when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}'
          then left(record.payload ->> 'data_protocolo', 4)::integer
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}'
          then left(record.payload ->> 'data_aprovacao', 4)::integer
      end,
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      nullif(btrim(coalesce(
        record.payload ->> 'autoria',
        record.payload ->> 'autor'
      )), ''),
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_indicacoes'
      and length(btrim(record.payload ->> 'id_indicacao')) > 0
      and length(btrim(record.payload ->> 'informacoes')) > 0
  ), latest as (
    select distinct on (candidates.item_kind, candidates.item_id)
      candidates.*
    from candidates
    order by candidates.item_kind, candidates.item_id, candidates.collected_at desc
  ), filtered as (
    select latest.*
    from latest
    where latest.author_name is not null
      and (item_kind_filter is null or latest.item_kind = item_kind_filter)
      and (year_filter is null or latest.reference_year = year_filter)
      and (author_filter is null or latest.author_name = nullif(btrim(author_filter), ''))
      and (
        query_filter is null
        or lower(concat_ws(
          ' ', latest.item_id, latest.title, latest.summary, latest.author_name
        )) like '%' || lower(btrim(query_filter)) || '%'
      )
  ), resolved as (
    select
      filtered.*,
      (
        select min(current_name.canonical_name)
        from current_names as current_name
        where current_name.name_key = lower(btrim(regexp_replace(
          regexp_replace(filtered.author_name, '\\([^)]*\\)', '', 'g'),
          '\\s+', ' ', 'g'
        )))
      ) as current_author_name
    from filtered
  )
  select resolved.current_author_name, count(*)::bigint
  from resolved
  where resolved.current_author_name is not null
  group by resolved.current_author_name
  order by count(*) desc, resolved.current_author_name;
end;
$function$;

revoke all on function api.get_camara_current_author_summary(text, integer, text, text)
  from public;
grant execute on function api.get_camara_current_author_summary(text, integer, text, text)
  to anon, authenticated;

comment on function api.get_camara_current_author_summary(text, integer, text, text) is
  'Resumo determinístico de leis e indicações atribuídas somente aos 19 vereadores da composição atual publicada pela Câmara.';
