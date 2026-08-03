# ADR 0021 — Histórico público navegável de fornecedor

## Status

Aceito — primeira versão.

## Decisão

Cada cartão de fornecedor na página de licitações aponta para uma página própria
com os processos PNCP associados, objeto, número de itens, valor homologado,
datas e fonte oficial. A consulta usa o mesmo identificador público do resumo e
deduplica resultados por compra, item e sequência.

## Motivo

Uma concentração isolada não deve ser tratada como anomalia, mas precisa ficar
visível para que uma repetição futura seja observável. O histórico torna essa
comparação auditável sem publicar CPF ou criar julgamento automático.

## Limitações

O histórico só cobre resultados PNCP já preservados. Ausência na página não
prova ausência em bases ainda não coletadas ou em documentos não publicados.
