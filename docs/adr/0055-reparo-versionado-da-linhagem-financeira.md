# ADR 0055: reparo versionado da linhagem financeira

- Status: aceito
- Data: 2026-08-11

## Contexto

Uma resposta da API municipal pode listar diversos meses e diversos PDFs. Parte
do acervo normalizado preservava o PDF correto, mas apontava para outro registro
bruto da mesma resposta agregada. Os valores continuavam ligados a um documento
oficial, porém a proveniência registro a registro não era exata. A projeção
pública passou a ocultar preventivamente essas linhas.

## Decisão

O reparo somente pode ocorrer quando três condições determinísticas coincidem:

1. o registro e o PDF pertencem ao mesmo artefato pai preservado;
2. o `source_record_key` do registro é igual ao metadado do PDF;
3. a URL HTTPS do registro é igual à URL oficial do PDF.

A linha antiga não é atualizada nem apagada. O sistema cria uma versão
append-only do vínculo documental em `finance.document_lineage_versions`, com
`supersedes_id`. A versão original registra a associação coletada e a versão
seguinte registra a origem efetiva comprovada. Os valores e linhas analíticas
não são recalculados nem duplicados. Cada reparo gera:

- uma entrada imutável em `audit.finance_lineage_repairs`;
- duas evidências, uma para o vínculo anterior e outra para o corrigido;
- um `evidence.source_conflicts` resolvido, com valores anterior e novo;
- uma operação idempotente, que não cria outra versão ao ser repetida.

Somente valores cobertos pela versão de linhagem exata voltam aos totais e
páginas públicas.

## Consequências

- jornalistas e auditores podem reconstruir o motivo de cada correção;
- o histórico permanece preservado, mesmo quando uma origem foi associada
  incorretamente;
- um único reparo documental corrige todas as linhas sustentadas pelo mesmo
  registro e PDF, evitando mais de 100 mil duplicações no acervo atual;
- o reparo não valida por si só o significado contábil nem recalcula valores;
- meses com mais de um relatório permanecem como `needs_review`, sem soma
  automática potencialmente duplicada;
- ausência temporária de valor público não pode ser interpretada como zero.
