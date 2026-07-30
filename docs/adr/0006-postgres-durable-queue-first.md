# ADR 0006 — Fila durável inicial no PostgreSQL

- Estado: Aceita
- Data: 2026-07-30

## Contexto

Workers precisam de retries, visibility timeout, idempotência e DLQ. Ainda não
há carga que justifique Redis/SQS/Kafka e outra infraestrutura.

## Decisão

Usar jobs duráveis no PostgreSQL com claim atômico,
`FOR UPDATE SKIP LOCKED`, lease expirável, tentativas máximas, backoff e estado
`dead_letter`. Processamento externo ocorre fora da transação. Mensagens
concluídas são arquivadas conforme retenção.

## Consequências

- operação e backup simples;
- coordenação transacional com metadados;
- polling e crescimento de tabela exigem métricas/índices;
- migrar para Supabase Queues/PGMQ ou broker externo exigirá ADR e teste de
  replay.

## Alternativas

- Fila em memória: rejeitada por perda e incompatibilidade multi-instância.
- Broker externo desde o início: adiado por custo operacional.
