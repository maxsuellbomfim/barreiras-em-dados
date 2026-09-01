begin;

-- A projeção pública parte das famílias documentais e conserva apenas a
-- observação mais recente de cada chave oficial. Sem este índice, o banco
-- percorre todo o acervo bruto antes de chegar aos poucos registros financeiros.
create index if not exists raw_records_finance_document_lookup_idx
  on raw.raw_records (
    record_type,
    source_record_key,
    created_at desc,
    id desc
  )
  where record_type in (
    'municipal_transparency_balancetes',
    'municipal_transparency_pdc-contas-anuais',
    'municipal_transparency_pdc-receita-tributaria',
    'municipal_transparency_pdc-recursos-extraordinarios',
    'municipal_transparency_pdc-resumo-execucao-da-receita',
    'municipal_transparency_pdc-resumo-execucao-da-despesa',
    'municipal_transparency_pdc-transferencia',
    'municipal_transparency_pdc-emendas-parlamentares-receitas',
    'municipal_transparency_pdc-convenios-transferencias-realizadas',
    'municipal_transparency_pdc-obras-pdc',
    'municipal_transparency_rreo',
    'municipal_transparency_rgf'
  )
  and payload ->> 'url' ~ '^https://';

-- O PDF/DOCX pode ter sido preservado por um replay diferente da resposta de
-- catálogo. O vínculo determinístico usa endpoint, chave oficial e URL da fonte.
create index if not exists raw_artifacts_municipal_document_identity_idx
  on raw.raw_artifacts (
    source_endpoint_id,
    (metadata ->> 'source_record_key'),
    source_url,
    created_at desc,
    id desc
  )
  include (sha256)
  where artifact_kind = 'document'
    and metadata ->> 'schema_name' = 'municipal-transparency-document';

commit;
