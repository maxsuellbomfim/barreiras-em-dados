# ADR 0059 — ranking objetivo de emendas e autoria coletiva

## Status

Aceita em 12/08/2026.

## Contexto

O Transferegov publica autor, tipo e valor da distribuição de recursos, além
de fatos financeiros posteriores. A população precisa comparar contribuições
comprovadas para Barreiras, mas uma comissão ou bancada não pode ser convertida
em autoria pessoal. Também não é correto somar valor destinado, empenhado e
pago como se fossem recursos diferentes.

## Decisão

- ativar o schema privado `territory` com projeções determinísticas ligadas aos
  registros e artefatos brutos;
- manter ranking pessoal separado de comissões, bancadas e demais autorias
  coletivas;
- ordenar por valor pago confirmado e, depois, por valor destinado, sem nota
  composta ou avaliação subjetiva;
- contar pagamento somente quando a ordem oficial estiver marcada como paga;
- quando uma proposta tiver mais de uma distribuição, não atribuir empenho ou
  pagamento a qualquer autor sem uma chave oficial que permita a divisão;
- deduplicar reexecuções pelo tipo e chave oficial do registro;
- mostrar ausência de estágio como “não encontrado na fonte consultada”, nunca
  como zero;
- ligar autoria individual a perfil político somente por crosswalk aprovado,
  sustentado pelo perfil oficial e por identificador eleitoral reconciliado;
- permitir diversas grafias oficiais para o mesmo perfil, preservando evidência
  por grafia e sem correspondência aproximada durante a consulta;
- expor somente RPCs no schema `api`; o browser não lê `territory` nem `raw`.

## Consequências

O painel permite competição cívica baseada em números verificáveis sem chamar
o resultado de avaliação geral do trabalho parlamentar. Leis, fiscalização,
presença, qualidade e execução do objeto permanecem métricas separadas. Novas
fontes poderão complementar a cobertura sem reescrever o bruto já preservado.
O perfil passa a mostrar valores destinados e pagos quando a associação estiver
aprovada; ausência de associação não é apresentada como ausência de atuação.
