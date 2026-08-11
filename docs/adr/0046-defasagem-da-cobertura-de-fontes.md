# ADR 0046 — Defasagem da cobertura das fontes

## Status

Aceito

## Contexto

O painel já distinguia cobertura completa, vazia, parcial, falha e bloqueio,
mas mostrava somente a data da última tentativa. Isso dificultava perceber
quando uma execução bem-sucedida processou um período antigo em relação ao
período que a fonte declarou.

## Decisão

O painel administrativo exibirá a defasagem aproximada entre o fim do período
da partição e a tentativa de coleta, calculada no navegador a partir dos
timestamps já sanitizados pela RPC. A métrica será descritiva, não um julgamento
de qualidade da fonte, e ficará separada do status da partição.

## Consequências

- Revisores identificam rapidamente fontes atrasadas sem consultar logs brutos.
- A métrica não altera estado, não cria partições e não transforma atraso em
  falha automaticamente.
- A classificação de cobertura continua sendo determinada pelo coletor e pelo
  banco; a UI apenas traduz a diferença temporal.
