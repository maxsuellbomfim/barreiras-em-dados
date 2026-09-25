begin;

-- A fila de aliases acumulava pendências que já estavam resolvidas: o
-- sugestor compara o nome exato (espaços, quebras de linha e caixa
-- diferentes geram outra sugestão) e nunca consultava os aliases aprovados.
-- Em 23/09/2026, 20 das 100 pendências já eram aliases aprovados e nomes
-- decididos pelo revisor tinham voltado à fila.
--
-- A fila passa a esconder, sem alterar status nem apagar nada, pendências
-- cujo nome normalizado (a mesma normalização do filtro público de autoria)
-- já é alias aprovado, nome canônico do elenco, ou já recebeu decisão de um
-- revisor; e mostra uma pendência por nome normalizado. A aceitação continua
-- exclusiva do revisor ativo.

create or replace function api.get_representative_alias_suggestions(
  page_size integer default 50
)
returns table (
  id uuid,
  observed_name text,
  source_record_keys text[],
  item_count integer,
  candidates jsonb,
  decision text,
  candidate_external_id text,
  alias_kind text,
  confidence numeric,
  rationale text,
  evidence jsonb,
  provider text,
  model text,
  prompt_version text,
  status text,
  created_at timestamptz
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
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;

  return query
  with resolved_keys as (
    select api.normalize_public_author_name(alias.alias_text) as name_key
    from political.representative_aliases as alias
    where alias.active
    union
    select api.normalize_public_author_name(alias.canonical_name)
    from political.representative_aliases as alias
    where alias.active
    union
    select api.normalize_public_author_name(record.payload ->> 'nome')
    from raw.raw_records as record
    where record.record_type = 'cm_barreiras_vereador'
      and record.payload ->> 'nome' is not null
    union
    select api.normalize_public_author_name(reviewed.observed_name)
    from political.representative_alias_suggestions as reviewed
    where reviewed.status <> 'pending'
  ),
  open_suggestions as (
    select distinct on (api.normalize_public_author_name(suggestion.observed_name))
      suggestion.*
    from political.representative_alias_suggestions as suggestion
    where suggestion.status = 'pending'
      and api.normalize_public_author_name(suggestion.observed_name)
        not in (select resolved.name_key from resolved_keys as resolved
                where resolved.name_key is not null)
    order by api.normalize_public_author_name(suggestion.observed_name),
      suggestion.created_at asc, suggestion.id asc
  )
  select
    suggestion.id,
    suggestion.observed_name,
    suggestion.source_record_keys,
    suggestion.item_count,
    suggestion.candidates,
    suggestion.decision,
    suggestion.candidate_external_id,
    suggestion.alias_kind,
    suggestion.confidence,
    suggestion.rationale,
    suggestion.evidence,
    suggestion.provider,
    suggestion.model,
    suggestion.prompt_version,
    suggestion.status,
    suggestion.created_at
  from open_suggestions as suggestion
  order by suggestion.created_at asc, suggestion.id asc
  limit page_size;
end;
$function$;

revoke all on function api.get_representative_alias_suggestions(integer)
  from public, anon;
grant execute on function api.get_representative_alias_suggestions(integer)
  to authenticated;

comment on function api.get_representative_alias_suggestions(integer) is
  'Fila de aliases pendentes para revisores ativos, sem nomes já cobertos por alias aprovado, elenco ou decisão anterior; uma pendência por nome normalizado.';

commit;
