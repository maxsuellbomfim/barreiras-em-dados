# ADR 0034 — Ajustes negativos na série de receitas

## Status

Aceita.

## Contexto

O demonstrativo sintético de arrecadação da Prefeitura de Barreiras pode
registrar uma linha negativa fora do grupo contábil `9.*`. No PDF de junho de
2026, por exemplo, a transferência de convênio registra `-3.776,33` no período,
mas mantém `696.223,67` no acumulado. Rejeitar o PDF inteiro apagaria a série
mensal; tratar toda a linha como dedução também distorceria o acumulado.

## Decisão

Linhas `9.*` continuam com `collection_direction = deduction`. Linhas fora
desse grupo que tenham qualquer componente negativo passam a ser classificadas
como `adjustment`. As magnitudes legadas continuam não negativas, mas a versão
1.1 do publicador também persiste os sinais originais de previsão, período e
acumulado em colunas próprias. A RPC pública 1.2 devolve esses sinais quando
disponíveis e mantém compatibilidade com linhas antigas.

O tipo do job de publicação foi versionado para que PDFs que falharam com a
regra antiga sejam reprocessados de forma idempotente, sem apagar jobs ou
artefatos históricos.

## Consequências

- O cidadão vê o ajuste separado de arrecadação e dedução do FUNDEB.
- O acumulado não recebe um sinal negativo artificial.
- Nenhum total é calculado por IA; o parser decimal e a RPC são determinísticos.
- Um ajuste continua sendo um fato do documento, não uma conclusão de
  irregularidade.
