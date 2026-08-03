# ADR 0026 — Filtros PNCP com chave normalizada

## Status

Aceito — primeira versão.

## Decisão

Os filtros de modalidade, situação e órgão passam a comparar uma chave
determinística compartilhada com o catálogo de sugestões. A chave normaliza
caixa, acentos e espaços repetidos, enquanto a resposta continua exibindo os
campos originais publicados pelo PNCP.

Uma nova RPC versionada foi criada para evitar quebra durante a transição. Os
filtros de fornecedor, ano e texto permanecem com a mesma semântica.

## Limitações

- A normalização não resolve abreviações ou nomes semanticamente equivalentes.
- O agrupamento não é uma conclusão sobre órgãos ou empresas.
- O vínculo com contratos e empenhos ainda depende de identificadores externos
  preservados em fontes específicas.

## Próxima etapa

Construir a projeção pública de contratações normalizadas e relacioná-la, quando
há identificador verificável, aos contratos, empenhos, liquidações e pagamentos.
