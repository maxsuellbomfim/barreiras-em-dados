# ADR 0016 — Reparar as projeções financeiras públicas

## Status

Aceito

## Contexto

Os coletores e o publicador financeiro já haviam preservado documentos e
gravado receitas validadas no Supabase, mas a página pública dependia de duas
funções no schema `api` que não estavam presentes na aplicação de produção.
Além disso, a função de receitas devolvia a versão interna do parser, enquanto
o cliente web validava a versão do contrato público.

## Decisão

Adicionar uma migration idempotente que:

1. cria a projeção `api.get_public_finance_documents` com o vínculo opcional ao
   PDF preservado;
2. mantém a versão pública dos documentos em `public-finance-documents/1.1.0`;
3. mantém a versão interna do parser fora do contrato público;
4. faz `api.get_public_revenues` devolver explicitamente
   `public-revenues/1.1.0`;
5. preserva os checks de publicação validada, hash, fonte e artefato filho.

## Consequência

Após a aplicação da migration e o deploy da aplicação web, os dados já
preservados tornam-se visíveis sem nova coleta. A correção não altera valores,
não reprocessa PDFs e não publica linhas que não estejam validadas.

