begin;

-- A lista pública já seleciona snapshots por chave PNCP e data de criação.
-- Sem estes caminhos, cada resultado lateral varre todo o acervo bruto.
-- Índices parciais mantêm outros tipos de registro fora do custo de manutenção;
-- não mudam snapshots, valores, JSON público, permissões nem regras editoriais.
create index raw_records_pncp_procurement_lookup_idx
  on raw.raw_records ((payload ->> 'numeroControlePNCP'), created_at desc)
  where record_type = 'pncp_contratacao';

create index raw_records_pncp_result_lookup_idx
  on raw.raw_records (
    (payload ->> 'numeroControlePNCPCompra'),
    (payload ->> 'numeroItem'),
    (payload ->> 'sequencialResultado'),
    created_at desc
  )
  where record_type = 'pncp_resultado';

commit;
