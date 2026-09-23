begin;

-- Lista leve das páginas próprias públicas para o sitemap: sem texto
-- integral, valores ou nomes. Só publica o que já tem página pública:
-- edições do Diário com documento publicado, contratações PNCP com número
-- de controle válido e fornecedores pessoa jurídica (CNPJ de 14 dígitos);
-- pessoa física nunca entra.

create function api.get_public_sitemap_entries()
returns table (
  entry_kind text,
  entry_key text,
  last_modified timestamptz
)
language sql
stable
security definer
set search_path = ''
as $function$
  select 'diario_edicao'::text,
    version.edition_year::text || '/' || version.edition::text,
    max(version.published_at)
  from editorial.gazette_document_versions as version
  where version.publication_status in ('validated', 'edition_fallback')
    and version.published_at is not null
  group by version.edition_year, version.edition
  union all
  select 'contratacao'::text,
    record.payload ->> 'numeroControlePNCP',
    max(record.created_at)
  from raw.raw_records as record
  where record.record_type = 'pncp_contratacao'
    and record.payload ->> 'numeroControlePNCP' ~ '^[0-9]{14}-[0-9]-[0-9]{6}/[0-9]{4}$'
  group by record.payload ->> 'numeroControlePNCP'
  union all
  select 'fornecedor'::text,
    record.payload ->> 'niFornecedor',
    max(record.created_at)
  from raw.raw_records as record
  where record.record_type = 'pncp_resultado'
    and record.payload ->> 'tipoPessoa' = 'PJ'
    and record.payload ->> 'niFornecedor' ~ '^[0-9]{14}$'
  group by record.payload ->> 'niFornecedor'
$function$;

revoke all on function api.get_public_sitemap_entries() from public;
grant execute on function api.get_public_sitemap_entries() to anon, authenticated;

comment on function api.get_public_sitemap_entries() is
  'Chaves das páginas próprias públicas (edições, contratações, fornecedores PJ) para o sitemap; sem conteúdo nem dado pessoal.';

notify pgrst, 'reload schema';

commit;
