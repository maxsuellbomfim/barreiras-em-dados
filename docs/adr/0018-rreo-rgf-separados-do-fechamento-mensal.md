# ADR 0018 — RREO e RGF separados do fechamento mensal

## Status

Aceita

## Contexto

A API de dados abertos da Prefeitura oferece demonstrativos mensais de execução
de despesas a partir de 2022, mas também oferece RREO e RGF com cobertura de
anos anteriores, inclusive 2021. Esses documentos têm periodicidade bimestral,
quadrimestral ou outra periodicidade fiscal e não são equivalentes a um mês de
receita ou despesa.

## Decisão

O catálogo público continuará exibindo todos os documentos, mas a interface
separará RREO/RGF em uma seção própria. O contrato do catálogo reconhecerá os
campos específicos `ano_ref` e `informacoes` usados por esses recursos. A
metodologia pública passa para `public-finance-documents/1.2.0`.

RREO/RGF podem sustentar contexto fiscal e cobertura histórica, mas não entram
automaticamente nos fechamentos mensais, saldos ou totais de despesas.

## Consequências

- O cidadão não confunde demonstrativo fiscal com um mês fechado.
- A cobertura de 2021 pode ser apresentada com a periodicidade correta.
- A ausência de despesas mensais anteriores a 2022 continua explicitamente
  documentada até que uma fonte compatível seja integrada.
- A alteração é idempotente e mantém os artefatos brutos e versões anteriores.
