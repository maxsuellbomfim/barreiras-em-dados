# ADR 0052 — Documentos-base de dívidas e obrigações

## Status

Aceito

## Contexto

O portal já explica que a diferença operacional mensal não equivale ao saldo
fiscal, mas ainda não preservava balancetes e contas anuais no workflow
financeiro. A projeção pública também restringia os registros a tipos `pdc-`,
apesar de RREO e RGF já integrarem a lista de fontes permitidas.

## Decisão

1. Coletar `balancetes` e `pdc-contas-anuais` junto com os demais documentos
   financeiros oficiais.
2. Corrigir a projeção para aceitar explicitamente todos os tipos permitidos,
   incluindo `municipal_transparency_rreo` e `municipal_transparency_rgf`.
3. Publicar esses artefatos em uma seção própria de obrigações em apuração.
4. Não calcular uma “dívida total” a partir de documentos isolados.

## Segurança e governança

A RPC mantém filtro de recursos em lista fechada, valida limite de página,
remove execução de `public` e concede somente a chamada controlada a `anon` e
`authenticated`. Nenhuma tabela bruta é exposta diretamente.

## Consequências

- O cidadão acompanha quais evidências já foram preservadas.
- Ausência de documento nunca é apresentada como dívida zero.
- A próxima etapa poderá extrair obrigações normalizadas com vínculo ao
  artefato, período e versão da fonte.
