# ADR 0042 — Painel administrativo de saúde das fontes

## Status

Aceita em 05/08/2026.

## Contexto

O controle central de coleta já distinguia partições completas, vazias,
parciais, falhas e bloqueadas, mas o operador precisava consultar banco e logs
para entender a cobertura. A ausência de uma visão consolidada facilitava
confundir “não coletado” com “a fonte não possui registros”.

## Decisão

Criar a RPC `api.get_collection_health`, restrita a revisores ativos, e uma aba
“Saúde das fontes” no painel administrativo. A RPC retorna todos os endpoints
habilitados, inclusive os que ainda não possuem partição controlada, além de
contagens agregadas e da falha sanitizada mais recente.

A projeção não retorna cursores de retomada, métricas brutas, erros internos de
execução, conteúdo de documentos, identificadores pessoais ou segredos. O
frontend não deduz atraso por um prazo arbitrário: apenas apresenta a idade da
última tentativa e os estados gravados pelo coletor.

Para o endpoint do Querido Diário, a projeção também calcula a faixa contínua de
partições `complete` ou `empty` associadas a execuções bem-sucedidas, desde o
horizonte de 01/01/2021. O painel mostra a próxima janela anterior de sete dias.
Partições isoladas não atravessam lacunas, e um vazio no agregador não é
apresentado como ausência de publicação na fonte oficial direta.

## Consequências

- “Vazio confirmado” e “sem execução controlada” tornam-se estados visivelmente
  distintos.
- Falhas pendentes e partições incompletas podem ser priorizadas sem acesso ao
  banco de produção.
- Novos coletores devem aderir ao controle central para deixarem de aparecer
  como sem cobertura.
- O avanço retroativo do Diário pode ser acompanhado sem consultar logs ou o
  banco, e a próxima janela permanece derivada de evidência persistida.
- Alertas por atraso dependerão de SLAs documentados por fonte em decisão
  futura.
