# ADR 0054 — Vínculo exato entre registro financeiro e PDF

## Status

Aceita em 11 de agosto de 2026.

## Contexto

Uma única resposta dos endpoints municipais pode listar diversos relatórios e
gerar vários artefatos PDF filhos. O catálogo público e os publicadores de
receitas e despesas relacionavam os filhos apenas pelo artefato HTTP pai. Dessa
forma, o PDF mais recente daquele lote podia ser atribuído a registros de meses
diferentes.

O coletor já grava `source_record_key` tanto no registro bruto quanto nos
metadados do PDF filho. A falha estava nas consultas de leitura, que não exigiam
a igualdade dessas chaves.

## Decisão

Todo consumo de `municipal-transparency-document` deve exigir simultaneamente:

1. o mesmo `parent_artifact_id` da resposta HTTP;
2. `metadata.schema_name = municipal-transparency-document`;
3. igualdade entre `document.metadata.source_record_key` e
   `raw_record.source_record_key`.

A projeção `api.get_public_finance_documents` passa à metodologia
`public-finance-documents/1.4.0`. Os publicadores de receitas e despesas aplicam
o mesmo predicado antes de analisar um PDF.

## Consequências

- um PDF não pode mais ser reutilizado acidentalmente para outro mês do lote;
- registros sem um filho de chave correspondente aparecem como ainda não
  preservados, em vez de receberem uma evidência incorreta;
- versões financeiras já publicadas não são alteradas ou apagadas;
- o acervo histórico deverá ser auditado e, quando houver divergência, gerar
  conflito e nova versão processada a partir do PDF correto.

## Verificação

O teste de migration cria dois registros e dois PDFs sob a mesma resposta HTTP,
com chaves e hashes distintos. A projeção só é aceita quando cada mês retorna o
hash do seu próprio documento.
