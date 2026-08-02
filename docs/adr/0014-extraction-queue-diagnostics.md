# ADR 0014 — Fila de atos com diagnóstico operacional

## Status

Aceita — 2026-08-02.

## Contexto

O painel administrativo mostrava candidatos com `assisted_enrichment`, mas a
função SQL da fila havia perdido o campo `assisted_payload` durante uma correção
de deduplicação. A interface então parecia vazia de IA, embora a sugestão
continuasse preservada em `raw.extraction_results`.

Também era impossível diferenciar, no primeiro olhar, três situações distintas:

- o trecho oficial não foi extraído;
- a cascata de IA ainda não respondeu;
- há trecho e sugestão, mas a conferência humana continua necessária.

## Decisão

A função `api.get_extraction_review_queue` passa a devolver:

- a sugestão assistida mais recente, sem promovê-la a fato;
- a URL da fonte quando disponível;
- `queue_reason`, com valores `missing_source_excerpt`,
  `ai_assistance_pending` ou `needs_human_verification`;
- metodologia `extraction-review-queue/1.6.0`.

O publicador automático continua limitado ao verificador determinístico de
campos literais. Nenhum resumo, sugestão ou reconstrução de IA decide sozinho.

## Operação

O workflow `Processar atos do Diário Oficial` processa documentos preservados
desde 2021, executa OCR pendente, tenta a cascata assistida e publica somente
atos aprovados pelo verificador. A execução é idempotente e pode ocorrer em
paralelo com a coleta diária.

## Consequências

O painel passa a explicar por que cada item está parado e exibe a fonte oficial.
O acervo antigo deixa de depender exclusivamente de uma nova coleta para ser
processado. Itens sem trecho continuam bloqueados e auditáveis, em vez de serem
publicados por inferência.
