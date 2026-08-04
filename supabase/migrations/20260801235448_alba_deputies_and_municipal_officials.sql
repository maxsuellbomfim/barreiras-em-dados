alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/',
        'alba/deputados/'
      ]
    )
  );

insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix,
  can_select, can_insert, status, activated_at, metadata
)
values (
  'alba-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'alba/deputados/',
  true, true, 'active', statement_timestamp(),
  jsonb_build_object('purpose', 'alba_raw_artifacts')
)
on conflict (auth_user_id, object_prefix) do nothing;

insert into source.data_sources (
  id, slug, name, description, authority_level, is_official,
  homepage_url, documentation_url, status
)
values (
  '00000000-0000-4000-8000-000000000009',
  'alba',
  'Assembleia Legislativa da Bahia',
  'Composicao da casa legislativa estadual publicada no portal oficial.',
  'official', true,
  'https://www.al.ba.gov.br/',
  'https://www.al.ba.gov.br/deputados/deputados-estaduais',
  'active'
)
on conflict (slug) do update
set name = excluded.name,
    description = excluded.description,
    documentation_url = excluded.documentation_url,
    status = excluded.status;

insert into source.source_endpoints (
  id, data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  '00000000-0000-4000-8000-000000000111',
  '00000000-0000-4000-8000-000000000009',
  'deputados-estaduais-html',
  'html',
  'https://www.al.ba.gov.br/deputados/deputados-estaduais',
  'GET', 10, 30, true,
  '{"observed_at": "2026-08-01", "nota": "sem dados abertos; listagem em <select> com id oficial", "cadeiras": 63}'::jsonb
)
on conflict (data_source_id, slug) do update
set base_url = excluded.base_url,
    rate_limit_per_minute = excluded.rate_limit_per_minute,
    request_timeout_seconds = excluded.request_timeout_seconds,
    enabled = excluded.enabled,
    config = excluded.config;

create or replace function api.get_state_deputies(
  page_size integer default 80
)
returns table (
  deputy_id text,
  display_name text,
  profile_url text,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200' using errcode = '22023';
  end if;

  return query
  select
    deputy.source_record_key,
    deputy.nome,
    deputy.perfil_url,
    deputy.collected_at,
    'state-deputies/1.0.0'::text
  from (
    select distinct on (record.source_record_key)
      record.source_record_key,
      record.payload ->> 'nome' as nome,
      record.payload ->> 'perfil_url' as perfil_url,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'alba_deputado_estadual'
      and record.payload ->> 'nome' is not null
    order by record.source_record_key, record.collected_at desc
  ) as deputy
  order by deputy.nome
  limit page_size;
end;
$function$;

revoke all on function api.get_state_deputies(integer) from public;
grant execute on function api.get_state_deputies(integer) to anon, authenticated;

comment on function api.get_state_deputies(integer) is
  'Deputados estaduais da Bahia, por identificador oficial da Assembleia.';

-- Secretarios e demais ocupantes de cargo municipal saem do proprio Diario:
-- a trajetoria e montada com os atos ja publicados, sem fonte nova.
create or replace function api.get_municipal_officials(
  page_size integer default 100
)
returns table (
  person_name text,
  position_title text,
  organization text,
  appointed_on date,
  dismissed_on date,
  current_status text,
  acts_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 300 then
    raise exception 'page_size deve estar entre 1 e 300' using errcode = '22023';
  end if;

  return query
  select
    trajectory.person_name,
    trajectory.position_title,
    trajectory.organization,
    trajectory.appointed_on,
    trajectory.dismissed_on,
    case
      when trajectory.dismissed_on is not null
       and (trajectory.appointed_on is null
            or trajectory.dismissed_on >= trajectory.appointed_on)
      then 'exonerado'
      when trajectory.appointed_on is not null then 'nomeado'
      else 'indefinido'
    end,
    trajectory.acts_count,
    'municipal-officials/1.0.0'::text
  from (
    select
      act.person_name,
      -- O cargo mais recente descreve a pessoa hoje.
      (array_agg(
         act.position_title order by act.gazette_date desc nulls last
       ) filter (where act.position_title is not null))[1] as position_title,
      (array_agg(
         act.organization order by act.gazette_date desc nulls last
       ) filter (where act.organization is not null))[1] as organization,
      max(act.gazette_date) filter (
        where act.act_type = 'nomeacao'
      ) as appointed_on,
      max(act.gazette_date) filter (
        where act.act_type = 'exoneracao'
      ) as dismissed_on,
      count(*)::int as acts_count
    from api.get_approved_gazette_acts(200) as act
    where act.person_name is not null
    group by act.person_name
  ) as trajectory
  order by
    greatest(
      coalesce(trajectory.appointed_on, '1900-01-01'::date),
      coalesce(trajectory.dismissed_on, '1900-01-01'::date)
    ) desc,
    trajectory.person_name
  limit page_size;
end;
$function$;

revoke all on function api.get_municipal_officials(integer) from public;
grant execute on function api.get_municipal_officials(integer)
  to anon, authenticated;

comment on function api.get_municipal_officials(integer) is
  'Trajetoria de ocupantes de cargo municipal derivada dos atos publicados.';;
