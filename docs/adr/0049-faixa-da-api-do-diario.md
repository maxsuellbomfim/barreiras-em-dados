# ADR 0049 — Faixa temporal da API do Diário

## Status

Aceito

## Contexto

O status público da API já informava a primeira e a última publicação
preservadas, mas a interface não explicava que esses valores são limites
observados e não prova de cobertura diária sem lacunas.

## Decisão

Exibir a faixa mínima/máxima de datas retornada pela API do Querido Diário e
explicar, junto dela, que dias sem edição ou sem coleta não podem ser inferidos
como equivalentes. O catálogo direto da Prefeitura permanece uma fonte
complementar e independente.

## Consequências

- O leitor consegue ver o alcance temporal da API sem interpretar a faixa como
  cobertura contínua.
- A metodologia continua baseada em registros preservados, não em estimativas.
- A busca por lacunas detalhadas continua pertencendo ao painel de saúde e às
  partições internas de coleta.
