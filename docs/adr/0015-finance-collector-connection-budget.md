# ADR 0015 — Orçamento de conexões do coletor financeiro

## Status

Aceita — 2026-08-02.

## Decisão

Os recursos do workflow financeiro são executados com `max-parallel: 1`.
Além disso, os workflows usam duas filas, correspondentes ao limite de duas
conexões da role. Coleta municipal e coleta documental compartilham
`municipal-finance-collection-production`; publicação de receitas, despesas,
comentários mensais e sinais compartilham
`municipal-finance-publication-production`. Ambas mantêm
`cancel-in-progress: false`.

O projeto usa uma role de coleta compartilhada em um plano gratuito, cujo limite
de conexões é menor que o número de recursos da matriz. A execução sequencial é
mais lenta, mas preserva idempotência, evita falhas intermitentes e não exige
abrir acesso de banco mais amplo.

## Consequência

Uma execução manual pode levar mais tempo, porém cada recurso é preservado sem
competir com os demais. No máximo uma coleta e uma publicação podem trabalhar
ao mesmo tempo; execuções da mesma classe aguardam a fila do GitHub Actions.
Usar duas filas, em vez de uma só, evita que uma coleta longa acumule e substitua
publicações ainda pendentes. A fila não apaga o histórico nem transforma falha
em ausência de dados.

O incidente de 14/08/2026 confirmou o risco: Transferegov, FIPLAN, LOA e a
publicação de receitas chegaram ao banco no mesmo intervalo e excederam o
limite de duas conexões da role. Depois da serialização interna, o replay isolado
do Transferegov (GitHub Actions `31855664796`) concluiu com sucesso e resolveu as
dez falhas pendentes, sem excluir os registros do incidente.
