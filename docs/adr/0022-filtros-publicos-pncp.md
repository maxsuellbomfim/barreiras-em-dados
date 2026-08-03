# ADR 0022 — Filtros públicos da área de compras

## Status

Aceito — primeira versão.

## Decisão

Adicionar uma projeção separada para filtrar contratações PNCP por fornecedor,
ano e texto no objeto ou unidade. A consulta continua lendo registros brutos
preservados, deduplica versões da contratação e devolve os valores informados
pela fonte com metodologia versionada.

Os filtros são GET e podem ser compartilhados por link. Quando há filtros, o
resumo agregado de fornecedores fica oculto para evitar misturar universos de
análise.

## Limitações

- A busca textual é literal e depende do texto publicado no PNCP.
- O fornecedor pode ser informado por CNPJ ou nome normalizado.
- Ainda não há filtros por secretaria normalizada nem por contrato/empenho.

## Próxima etapa

Normalizar contratos e itens e adicionar filtros por órgão, modalidade e estágio
financeiro.
