# ADR 0024 — Sugestões de filtros baseadas no PNCP preservado

## Status

Aceito — primeira versão.

## Decisão

A interface de compras passa a oferecer sugestões para modalidade, situação e
órgão ou unidade usando somente valores observados nos registros PNCP brutos e
preservados. Cada sugestão informa quantas contratações deduplicadas a utilizam.

As sugestões são auxiliares: o usuário ainda pode digitar um valor diferente,
porque o catálogo pode estar incompleto enquanto a coleta histórica avança.
Nenhuma categoria é inferida por IA ou criada por aproximação textual.

## Limitações

- A lista é limitada às 50 primeiras opções de cada tipo para manter a página
  leve.
- Diferenças de grafia publicadas pelo PNCP continuam sendo opções distintas.
- O contador representa a janela de registros preservados, não todo o universo
  de contratações do município.

## Próxima etapa

Normalizar órgãos e modalidades para reduzir variações de grafia e relacionar
contratações aos contratos, empenhos e pagamentos disponíveis.
