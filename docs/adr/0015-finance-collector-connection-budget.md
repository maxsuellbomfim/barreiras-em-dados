# ADR 0015 — Orçamento de conexões do coletor financeiro

## Status

Aceita — 2026-08-02.

## Decisão

Os recursos do workflow financeiro são executados com `max-parallel: 1`.

O projeto usa uma role de coleta compartilhada em um plano gratuito, cujo limite
de conexões é menor que o número de recursos da matriz. A execução sequencial é
mais lenta, mas preserva idempotência, evita falhas intermitentes e não exige
abrir acesso de banco mais amplo.

## Consequência

Uma execução manual pode levar mais tempo, porém cada recurso é preservado sem
competir com os demais. A publicação de receitas pode ser executada depois da
coleta, com o mesmo limite de conexão seguro.
