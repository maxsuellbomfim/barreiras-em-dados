# ADR 0089 — Fonte externa indisponível como falha tratada

## Status

Aceita em 28/09/2026 pelo titular ("pode seguir com os prazos sugeridos e o
piloto da CGU"). Piloto: sanções da CGU.

## Contexto

O gate de prontidão exige sete execuções agendadas consecutivas sem falha
não tratada. Entre 21 e 27/09, as falhas restantes vieram de fontes externas
fora do ar (API de sanções da CGU, catálogo estadual de emendas da Bahia,
consulta de contratações do PNCP). Todo passo com erro deixava o workflow
vermelho, então uma API externa instável pesava como um defeito nosso e a
contagem nunca fechava.

## Decisão

1. **Três classes de falha**, decididas pelo coletor por regra fixa:
   - *fonte indisponível*: nada chegou depois das novas tentativas (tempo
     esgotado, erro de conexão/TLS, HTTP 408/425/429/5xx, circuito aberto);
   - *quebra de contrato*: a resposta chegou, mas diverge do contrato
     (formato, hash, unidade, autenticação recusada);
   - *falha interna*: banco, Storage ou código nosso.
   Só a primeira é marcada, com a classe `SourceUnavailable`
   (`barreiras_collectors.source_availability`).
2. **Registro não muda.** A falha continua em `source.collection_failures`,
   com nova tentativa agendada; nada vira zero nem some da cobertura.
3. **Código de saída.** Fonte indisponível dentro do prazo sai com 75
   (EX_TEMPFAIL); o passo do workflow emite aviso e termina verde. Qualquer
   outro código mantém o job vermelho.
4. **Prazo.** O prazo é o da política de atualização do endpoint
   (`freshness_expected_hours + freshness_grace_hours`), medido desde a
   última execução `succeeded` do endpoint (execução `partial` não conta: o
   PNCP fora do ar termina parcial e esconderia uma queda longa). Além do prazo,
   ou sem política `scheduled`, a indisponibilidade sai com 1: vira falha
   não tratada e quebra a contagem de prontidão.
5. **Prazos acordados:** sanções da CGU 72 h (24 + 48); catálogo estadual de
   emendas da Bahia 7 dias; PNCP 48 h.
6. **PNCP:** a coleta de contratações termina `partial` quando modalidades
   falham. Só vira aviso quando **todas** as falhas foram indisponibilidade
   (`PncpUnavailable`, incluindo HTTP 429) e nenhuma modalidade foi truncada;
   resposta que chega e não fecha (contagem divergente, inconclusiva) continua
   vermelha. As falhas de 21 a 25/09 eram janelas retroativas parciais, não
   indisponibilidade, e continuam vermelhas.

## Consequências

- A prontidão passa a medir o que controlamos, sem esconder fonte fora do ar:
  o aviso fica no workflow, a falha fica no banco e a reconciliação
  (`source.reconcile_collection_failures`) fecha quando a fonte volta.
- Queda longa continua vermelha por construção.
- Próximos passos: catálogo estadual da Bahia e PNCP, cada um com seu prazo;
  depois, uma coluna de classe em `collection_failures` se o painel precisar
  separar as classes.

## Alternativas descartadas

- `continue-on-error` nos passos: esconderia quebras de contrato.
- Mais novas tentativas: não resolve queda de vários dias.
- Tirar esses workflows do gate: esconde o problema em vez de tratá-lo.
