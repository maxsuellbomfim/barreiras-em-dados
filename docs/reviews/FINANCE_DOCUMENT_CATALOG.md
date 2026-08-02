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
- parser determinístico inicial para o `Demonstrativo de Receita Orçamentária
  Sintético`, com suporte a valores negativos de deduções e testes unitários;
- mensagem pública explícita quando a ausência de números ainda for uma
  etapa de validação, e não receita zero.

## Limite atual

O workflow preserva a resposta da API e aponta para o documento oficial. Ele
ainda não publica valores extraídos dos PDFs. Essa próxima etapa exige parser
específico por relatório, testes com fixtures reais sanitizadas, reconciliação
de período e revisão humana antes da publicação.

O parser inicial já reconhece o layout textual desse demonstrativo quando o
PDF passa pelo extrator de texto. Ele permanece deliberadamente separado da
publicação: uma integração futura deverá baixar o PDF como artefato filho,
registrar a versão do extrator, comparar totais e só então gerar linhas em
`finance.revenues`.

## Procedimento de ativação

1. Aplicar a migration `20260804030000_public_finance_documents.sql` no projeto
   Supabase de produção.
2. Conferir se as variáveis e secrets usados pelo workflow municipal continuam
   válidos.
3. Executar manualmente `Coletar documentos financeiros municipais` para uma
   matriz pequena e revisar o status da coleta.
4. Conferir `/financas`; a seção de documentos deve aparecer antes dos números.
5. Só depois iniciar a extração de RREO, RGF, receitas e despesas com fixtures e
   validação de qualidade.
