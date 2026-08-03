# ADR 0020 — Cruzamento inicial de fornecedores no PNCP

## Status

Aceito — primeira versão exploratória.

## Contexto

Os resultados do PNCP chegam inicialmente como registros brutos preservados.
Antes de normalizar toda a malha societária, já é possível oferecer uma leitura
útil e reproduzível de quem venceu itens e em quantos processos.

## Decisão

`api.get_public_supplier_concentration` deduplica resultados por compra, item e
sequência do resultado, agrupa por identificador público do fornecedor e calcula
quantidade de processos, itens, valor homologado e participação na janela
observada.

O indicador `attention_signal` só é verdadeiro quando há recorrência em pelo
menos três processos ou quando há pelo menos dois processos e participação de
50% ou mais. Um processo grande isolado não gera alerta.

## Limitações

- A janela depende do acervo PNCP já preservado; não representa todo o histórico
  municipal.
- Participação de valor não mede sobrepreço, qualidade ou legalidade.
- O cruzamento societário, CEIS/CNEP e contratos ainda não fazem parte desta
  etapa.

## Próxima etapa

Normalizar compras e contratos em tabelas próprias, ligar empenhos quando
disponíveis e permitir filtros por período, órgão e fornecedor.
