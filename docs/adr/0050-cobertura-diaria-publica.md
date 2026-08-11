# ADR 0050 — Cobertura diária pública do Diário

## Status

Aceito

## Contexto

A faixa mínima/máxima de datas não mostra onde existem lacunas. O painel
administrativo já possui uma visão diária interna, mas o cidadão não tinha
como distinguir uma janela coletada sem edição de um dia ainda não classificado.

## Decisão

Criar uma RPC pública somente de agregados diários, limitada e paginada. Cada
dia retornará `complete`, `empty` ou `unclassified`, junto apenas da quantidade
de edições e documentos preservados. A página exibirá a janela recente em uma
sanfona recolhida; dados brutos, URLs internas e falhas detalhadas continuam
restritos ao painel.

## Consequências

- A população pode verificar a qualidade temporal da coleta sem acessar dados
  internos ou sensíveis.
- “Unclassified” nunca será apresentado como dia vazio.
- A lista pública é um resumo operacional, não substitui o Diário Oficial nem
  garante que toda publicação municipal tenha sido coletada.
