# Finanças: catálogo de documentos e números validados

## Diagnóstico

A API de dados abertos da Prefeitura responde aos recursos financeiros com um
catálogo de documentos. Uma amostra observada em 02/08/2026 retornou campos como
`titulo`, `data`, `ano`, `mes`, `descricao` e `url` para
`pdc-resumo-execucao-da-receita`; ela não retornou um campo numérico de receita.

Por isso, a página pública não deve fabricar totais a partir do título ou do
nome do arquivo. O fluxo correto é:

```text
API municipal → resposta bruta preservada → documento oficial → extração
validada → revisão → finance.revenues → projeção pública
```

## O que foi implementado

- catálogo municipal versionado em `fixtures/sources/municipal-source-catalog.json`;
- schema e verificação de fontes no CI;
- função `api.get_public_finance_documents`;
- página `/financas` com duas camadas:
  - números somente quando `finance.revenues` estiver normalizada;
  - documentos oficiais e trilha de evidência quando a fonte ainda for PDF;
- workflow diário para preservar os catálogos financeiros da Prefeitura;
- preservação do PDF apontado por cada registro como artefato filho imutável,
  com allowlist exclusiva de `barreiras.mtransparente.com.br`, hash e vínculo
  ao artefato JSON pai;
- associação exata entre registro e PDF por `source_record_key`, impedindo que
  relatórios distintos de uma mesma resposta da API compartilhem por engano o
  artefato filho mais recente;
- parser determinístico inicial para o `Demonstrativo de Receita Orçamentária
  Sintético`, com suporte a valores negativos de deduções e testes unitários;
- contrato de assistência em cascata para classificar o relatório e sugerir
  linhas com âncora literal, sem permitir que a IA calcule números;
- contrato publicável e publicador idempotente para o primeiro demonstrativo de
  receita, com deduções assinadas e status `validated`;
- workflow separado para publicar uma janela financeira por ano, com backfill
  inicial a partir de 2021;
- mensagem pública explícita quando a ausência de números ainda for uma
  etapa de validação, e não receita zero.

## Limite atual

O workflow preserva a resposta da API e o PDF oficial quando o endpoint entrega
um link válido. O publicador grava somente linhas com validação determinística,
preserva a direção contábil das deduções e liga cada linha ao JSON pai e ao PDF
filho.

Versões publicadas antes do vínculo exato são mantidas imutáveis e entram em
auditoria de evidência. Qualquer correção será uma nova versão rastreável, nunca
uma atualização silenciosa do registro histórico.

O parser inicial reconhece o layout textual desse demonstrativo quando o PDF
passa pelo extrator de texto. Páginas sem texto embutido permanecem fora da
publicação até o estágio de OCR; elas não são tratadas como receita zero.

## Procedimento de ativação

1. Aplicar as migrations `20260804030000_public_finance_documents.sql`,
   `20260804040000_finance_document_artifacts.sql` e
   `20260805010000_finance_revenue_automation.sql` no projeto Supabase de
   produção.
2. Conferir se as variáveis e secrets usados pelo workflow municipal continuam
   válidos.
3. Executar manualmente `Coletar documentos financeiros municipais` para uma
   matriz pequena e revisar o status da coleta.
4. Executar `Publicar receitas financeiras validadas` com `limit=1` e o ano do
   primeiro relatório coletado.
5. Conferir `/financas`; somente linhas `validated` devem aparecer, com PDF,
   hash, direção contábil e metodologia.
6. Ampliar o backfill por ano após conferir a primeira janela; anos sem fonte
   validada devem continuar visíveis como ausência de cobertura, não como zero.
