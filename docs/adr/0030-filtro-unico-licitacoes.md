# ADR 0030 — Um único filtro canônico para licitações

## Status

Aceito

## Contexto

A página pública de licitações apresentava dois conjuntos de filtros para a mesma
lista: um formulário GET que consultava a RPC normalizada do PNCP e outro filtro
local no navegador. Além de ocupar espaço, os dois estados podiam divergir e
faziam parecer que a lista não correspondia à consulta oficial.

## Decisão

Manter somente o formulário GET no servidor como filtro canônico. Os resultados
exibidos pelo explorador são exatamente o conjunto devolvido pela consulta
filtrada do PNCP. O explorador calcula apenas a soma dos valores homologados dos
registros já recebidos; não aplica uma segunda filtragem no navegador.

O formulário foi reorganizado em uma grade responsiva, com campos de busca,
fornecedor, ano, modalidade, situação e órgão. A página informa explicitamente
que os resultados abaixo já correspondem aos filtros aplicados.

## Consequências

- Há uma única fonte de verdade para filtros e paginação.
- URLs com filtros continuam reproduzíveis e compartilháveis.
- O navegador deixa de manter estado duplicado e reduz a chance de mostrar um
  total diferente do resultado oficial.
- Novos filtros devem ser adicionados à consulta server-side e aos contratos de
  dados antes de receber controles na interface.
