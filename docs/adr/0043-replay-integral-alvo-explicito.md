# ADR 0043 — Replay integral com alvo explícito

## Status

Aceita

## Contexto

O comando de segmentação do Diário é idempotente e, normalmente, pode não
encontrar novos artefatos sem que isso represente uma falha. Em um replay
direcionado, porém, `--edition` e `--edition-year` expressam uma expectativa
operacional: a edição solicitada precisa ter sido preservada e estar elegível
para processamento. Encerrar com sucesso e `processed=0` escondia erro de
descoberta, data, ano ou preservação incompleta.

## Decisão

O resultado do segmentador passa a registrar `matched` e `skipped` nos logs.
Quando uma edição específica é solicitada e nenhuma edição elegível é
encontrada, o comando registra `integral_gazette_target_not_found` e retorna
código 2. Coletas sem alvo explícito permanecem idempotentes: zero novos
documentos continua sendo um resultado válido quando não há pendências.

## Consequências

- Replays incorretos ou incompletos ficam visíveis no GitHub Actions e geram
  falha sanitizada para diagnóstico.
- Reprocessamentos já concluídos continuam seguros e não duplicam versões.
- O log permite distinguir edição encontrada e ignorada por idempotência de
  edição nunca preservada.
- O comportamento não publica conteúdo nem altera artefatos históricos.
