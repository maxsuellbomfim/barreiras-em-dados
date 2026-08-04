-- Projeta campos biográficos transcritos das páginas individuais da ALBA.

update source.source_endpoints
set config = jsonb_set(
  config,
  '{parser_version}',
  '"alba-deputado-profile/1.1.0"'::jsonb,
  true
)
where slug = 'deputado-estadual-profile-html'
  and data_source_id = (select id from source.data_sources where slug = 'alba');

drop function if exists api.get_state_representatives(integer);

create function api.get_state_representatives(
  page_size integer default 100
)
returns table (
  external_id text,
  display_name text,
  profile_url text,
  photo_url text,
  education text,
  professional_activity text,
  elective_mandate text,
  parliamentary_activity text,
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
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;

  return query
  select
    deputy.external_id,
    deputy.display_name,
    deputy.profile_url,
    case
      when profile.payload ->> 'foto_url' ~ '^https://www\.al\.ba\.gov\.br/fserver/'
        then profile.payload ->> 'foto_url'
      else null
    end as photo_url,
    profile.payload ->> 'formacao_educacional' as education,
    profile.payload ->> 'atividade_profissional' as professional_activity,
    profile.payload ->> 'mandato_eletivo' as elective_mandate,
    profile.payload ->> 'atividade_parlamentar' as parliamentary_activity,
    deputy.collected_at,
    'state-representatives/alba/1.2.0'::text
  from (
    select distinct on (record.payload ->> 'id_alba')
      record.payload ->> 'id_alba' as external_id,
      btrim(record.payload ->> 'nome') as display_name,
      record.payload ->> 'perfil_url' as profile_url,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'alba_deputado_estadual'
      and record.payload ->> 'id_alba' ~ '^[0-9]+$'
      and length(btrim(record.payload ->> 'nome')) > 0
      and record.payload ->> 'perfil_url' ~ '^https://www\.al\.ba\.gov\.br/deputados/deputado-estadual/[0-9]+$'
    order by
      record.payload ->> 'id_alba',
      record.collected_at desc
  ) as deputy
  left join lateral (
    select record.payload
    from raw.raw_records as record
    where record.record_type = 'alba_deputado_estadual_profile'
      and record.payload ->> 'id_alba' = deputy.external_id
    order by record.collected_at desc
    limit 1
  ) as profile on true
  order by deputy.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_state_representatives(integer) from public;
grant execute on function api.get_state_representatives(integer)
  to anon, authenticated;

comment on function api.get_state_representatives(integer) is
  'Composição estadual da ALBA; campos biográficos são transcrições da página oficial e não criam vínculo automático com Barreiras.';
