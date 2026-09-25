begin;

-- finance.get_exact_document_lineage_pairs() sustenta todas as RPCs públicas
-- de Finanças e é recalculada a cada chamada. Sem estes índices, o banco
-- percorria os 11 mil PDFs do dreno TCM-BA e ~126 mil registros das páginas
-- municipais para achar poucas centenas de pares, passando do statement
-- timeout de 3 s do papel anon (/financas e /api/health degradados desde
-- 21/09/2026). Os índices espelham literalmente os predicados da função;
-- nenhuma regra de linhagem, contrato ou valor muda.

-- Linhagem municipal: registro da página -> PDF filho pela mesma chave.
create index if not exists raw_records_artifact_source_key_idx
  on raw.raw_records (raw_artifact_id, source_record_key)
  where source_record_key is not null;

-- Linhagem TCM-BA: parte dos ~150 demonstrativos PCMGE015/016, não dos
-- 177 mil registros do catálogo mensal.
create index if not exists raw_records_tcm_ba_finance_lineage_idx
  on raw.raw_records (source_record_key, raw_artifact_id)
  where record_type = 'tcm_ba_monthly_document'
    and source_record_key is not null
    and left(payload ->> 'category', 8) in ('PCMGE015', 'PCMGE016');

analyze raw.raw_records;

commit;
