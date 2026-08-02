# Revisão da exploração pública de contratações

Data: 2026-08-02

## Escopo

A página `/licitacoes` passou a permitir busca e filtros locais sobre os
registros já publicados pelo PNCP. O filtro pesquisa objeto, unidade,
modalidade, situação e fornecedor; também há filtros independentes por ano e
modalidade.

## Regras de interpretação

- O conjunto exibido continua limitado ao retorno preservado pelo RPC público;
  filtros não fazem nova coleta e não representam cobertura total do PNCP.
- A soma mostrada é calculada deterministicamente no navegador apenas sobre os
  valores homologados não nulos dos registros filtrados. Ela é rotulada como
  “soma dos valores homologados carregados” e não como total municipal.
- Valores ausentes permanecem “não informado”; ausência de resultado não é
  convertida em zero.
- Cada cartão mantém o link para o registro oficial no PNCP e o identificador
  do processo.
- A busca não classifica empresas, pessoas ou contratações e não produz
  inferências reputacionais.

## Verificações executadas

- `pnpm --filter @barreiras-em-dados/web typecheck`
- `pnpm --filter @barreiras-em-dados/web build`
- `npm test`
- `git diff --check`

Todos passaram em ambiente local. O aviso de engine é apenas a diferença entre
Node 24 local e Node 22.x declarado pelo monorepo.
