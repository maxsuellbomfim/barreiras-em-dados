# ADR 0031 — Preservação de contratos e empenhos do PNCP

## Status

Aceito

## Contexto

A página de licitações já preserva a contratação, seus itens e seus resultados,
mas a execução financeira ainda aparece como `not_normalized` porque contratos,
empenhos, liquidações e pagamentos não devem ser associados por texto ou valor.
O manual oficial do PNCP fornece um endpoint determinístico para recuperar os
contratos/empenhos de uma contratação.

## Decisão

Adicionar o endpoint `contratos-api` e um coletor limitado a 50 contratações por
execução. O coletor consulta
`/v1/orgaos/{cnpj}/contratos/contratacao/{ano}/{sequencial}`, valida que cada
registro retorna `numeroControlePNCPCompra` igual à contratação solicitada e
preserva a resposta bruta com hash, URL, cursor e versão do parser.

Nesta etapa, os registros permanecem em `raw.raw_records` como
`pncp_contrato`. Nenhum valor é inserido nas tabelas normalizadas de contratos
ou execução financeira antes de um contrato de normalização com fixture real,
regras de versão e testes de idempotência.

## Consequências

- Contratos/empenhos passam a ter evidência preservada e replayável.
- O painel continua honesto: a execução só será marcada como ligada quando as
  tabelas normalizadas tiverem vínculos oficiais.
- Respostas sem vínculo com a contratação são rejeitadas como erro de contrato,
  em vez de contaminar o histórico.
- A próxima etapa pode normalizar contratos e empenhos usando o identificador
  PNCP, sem alterar o acervo bruto.
