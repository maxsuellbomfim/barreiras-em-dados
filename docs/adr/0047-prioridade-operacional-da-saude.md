# ADR 0047 — Prioridade operacional na saúde das fontes

## Status

Aceito

## Contexto

O painel informava o atraso, mas mantinha a ordem retornada pela API. Em uma
lista grande, falhas e fontes atrasadas podiam ficar distantes umas das outras,
reduzindo o valor operacional do diagnóstico.

## Decisão

No navegador, a lista será ordenada de forma estável por prioridade: falhas e
bloqueios, atenção/parcial, ausência de execução e, por fim, fontes saudáveis.
Dentro de cada grupo, a maior defasagem temporal aparece primeiro. A ordenação
é apenas de apresentação e não altera o status persistido nem a metodologia da
coleta.

## Consequências

- A primeira tela do painel passa a indicar o que merece intervenção imediata.
- A busca continua funcionando antes da ordenação e os contadores permanecem
  referentes ao conjunto carregado.
- Nenhum atraso é convertido automaticamente em acusação ou falha técnica.
