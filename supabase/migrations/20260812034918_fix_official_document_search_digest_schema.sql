-- O Supabase instala pgcrypto no schema extensions. A versao anterior do
-- trigger qualificava digest como public.digest e falhava somente no banco
-- remoto, revertendo a evidencia antes de registrar a cobertura do catalogo.

create or replace function source.verify_official_document_search_evidence()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  linked_count integer;
  computed_manifest text;
begin
  select
    count(*)::integer,
    encode(
      extensions.digest(
        string_agg(
          link.raw_artifact_id::text || ':' || artifact.sha256,
          E'\n' order by link.artifact_order
        ),
        'sha256'
      ),
      'hex'
    )
  into linked_count, computed_manifest
  from source.official_document_search_artifacts as link
  join raw.raw_artifacts as artifact
    on artifact.id = link.raw_artifact_id
   and artifact.artifact_kind = 'http_response'
  where link.official_document_search_id = new.id;

  if linked_count <> new.evidence_artifact_count
     or computed_manifest is distinct from new.evidence_manifest_sha256::text then
    raise exception 'official document search evidence manifest mismatch'
      using errcode = '23514';
  end if;
  return null;
end;
$function$;

revoke all on function source.verify_official_document_search_evidence()
  from public, anon, authenticated;
