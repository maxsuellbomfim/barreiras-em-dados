# Etapa 2A — preservação de contratos e empenhos do PNCP

Data: 03/08/2026.

## Fonte confirmada

O Manual de Integração do PNCP v. 2.5 documenta o endpoint:

`GET /v1/orgaos/{cnpj}/contratos/contratacao/{anoContratacao}/{sequencialContratacao}`

O retorno contém uma lista de contratos/empenhos ligados à contratação, com
`numeroControlePNCP`, `numeroControlePNCPCompra`, fornecedor, objeto, valores,
vigência e data de publicação.

## Escopo desta etapa

- cadastrar o endpoint `contratos-api`;
- coletar até 50 contratações por execução;
- preservar a resposta JSON como artefato imutável com hash;
- registrar cada contrato como `pncp_contrato` ligado ao controle da contratação;
- rejeitar resposta cujo `numeroControlePNCPCompra` não corresponda ao pedido.

Os registros ainda não são convertidos em `procurement.contracts` ou
`finance.commitments`. A execução financeira continuará aparecendo como
`not_normalized` até que exista uma normalização determinística com fixture real,
idempotência e testes de versão.
