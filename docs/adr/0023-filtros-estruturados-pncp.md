# ADR 0023 — Filtros estruturados para compras públicas

## Status

Aceito — primeira versão.

## Decisão

Além do texto livre, a área de compras passa a oferecer filtros estruturados por
modalidade, situação e órgão ou unidade. Eles são comparações determinísticas
com os valores publicados no PNCP, ignorando diferenças de maiúsculas e
minúsculas, sem inferir ou classificar o conteúdo.

A consulta usa uma nova função RPC versionada para manter compatibilidade com a
função anterior e evitar indisponibilidade durante a implantação.

## Limitações

- As opções são informadas pelo usuário e precisam corresponder ao texto
  publicado pelo PNCP.
- O filtro de órgão usa o campo de unidade publicado na contratação.
- Ainda não há filtros normalizados por secretaria, contrato ou estágio de
  empenho, porque esses vínculos exigem uma camada de normalização própria.

## Próxima etapa

Catalogar modalidades e unidades observadas para oferecer sugestões na
interface e depois relacionar contratações a contratos, empenhos e pagamentos.
