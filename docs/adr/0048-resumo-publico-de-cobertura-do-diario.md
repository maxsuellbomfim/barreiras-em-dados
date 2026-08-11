# ADR 0048 — Resumo público de cobertura do Diário

## Status

Aceito

## Contexto

O Diário Oficial passou a ter paginação e busca global, mas o leitor ainda
precisava inferir se estava vendo o acervo inteiro ou apenas uma página. O
catálogo oficial e a preservação integral também têm estados diferentes.

## Decisão

A página pública exibirá três contadores com rótulos explícitos: edições
integrais preservadas no acervo, registros do catálogo oficial consultado e
edições carregadas na página atual. Quando o status da coleta não estiver
disponível, o primeiro contador permanecerá como indisponível, nunca como zero.

## Consequências

- O cidadão entende a diferença entre acervo total, catálogo e paginação.
- A interface não promete que o catálogo consultado seja a totalidade histórica.
- Nenhum contador é calculado somando documentos ou inferindo ausência de fonte.
