# Revisão da exploração pública de atos

Data: 2026-08-02

## Escopo

A página `/atos` passou a permitir busca por nome, cargo, símbolo, órgão,
trecho e resumo; filtros por nomeação/exoneração e órgão; e período por data
do ato. A filtragem acontece no navegador sobre o conjunto de atos que já foi
aprovado e publicado pela API pública.

## Regras de interpretação

- Os filtros não fazem nova coleta e não ampliam a cobertura do Diário Oficial.
- Atos sem data estruturada não entram quando um período é informado; isso é
  diferente de afirmar que o ato não existe.
- A contagem é sempre rotulada como subconjunto dos atos publicados.
- Cada cartão mantém documento, trecho, hash e modo de revisão.
- O filtro não cria avaliação sobre pessoas e não altera decisões editoriais.

## Verificações executadas

- `pnpm --filter @barreiras-em-dados/web typecheck`
- `pnpm --filter @barreiras-em-dados/web build`
- `npm test`
- `git diff --check`
