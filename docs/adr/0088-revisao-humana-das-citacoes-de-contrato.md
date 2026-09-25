# ADR 0088 — Revisão humana das citações de contrato

## Status

Aceita em 24/09/2026 por pedido do titular ("prossiga com a fila de revisão").

## Contexto

A regra do ADR 0086 confirmou 21.121 ligações empenho → contrato entre
janeiro de 2024 e agosto de 2026 e deixou 13.516 citações sem confirmação.
Duas razões têm um contrato candidato e dependem só de julgamento humano:

- `favorecido_divergente` (6.385): o número aponta para um contrato único,
  mas o nome do favorecido não é igual ao do contratado. A amostra mostra os
  dois casos: a mesma empresa escrita de outro jeito ("J S COMERCIO" ×
  "JS COMERCIO", nome abreviado no cadastro) e empresas diferentes (número de
  contrato de outra empresa citado no histórico);
- `varios_contratos` (133): o portal cadastrou o mesmo número mais de uma vez.

As citações repetem muito (um fornecedor de combustível citou o mesmo
contrato em 750 empenhos), então revisar empenho por empenho é inviável.

## Decisão

- A regra determinística grava, em `finance.commitment_link_candidates`
  (append-only), os contratos que o número citado aponta. O SQL não
  reimplementa a normalização.
- A fila agrupa as citações pendentes por motivo, favorecido e contrato(s)
  candidato(s). Uma decisão vale para o grupo e é gravada **por ligação** em
  `editorial.editorial_reviews` (`target_type =
  'finance.commitment_contract_links'`), com revisor, justificativa
  obrigatória e, ao confirmar, o contrato escolhido no checklist.
- Decisões: `approved` (mesma empresa; exige escolher um candidato),
  `rejected` (empresa diferente) e `changes_requested` (pedir evidência, que
  mantém o grupo na fila). As RPCs exigem revisor ativo com MFA
  (`api.is_active_reviewer`) e nunca ficam abertas ao `anon`.
- A projeção pública passa a incluir as confirmações humanas com
  `review_mode = 'human'` e o rótulo "confirmada por revisão humana". Uma
  revisão posterior `withdrawn` retira a ligação, como nas automáticas.
- `nenhum_contrato` (6.974), `numero_ilegivel`, `multiplas_citacoes` e
  extra-orçamentários ficam fora desta fila: não há contrato preservado para
  confirmar.

## Consequências

- O revisor resolve centenas de empenhos com uma decisão auditável, sem
  perder o registro individual.
- Um erro de revisão publicaria ligação incorreta com rótulo humano;
  mitigação: justificativa obrigatória, amostra de empenhos e documento do
  contrato no cartão, e retirada auditada.
- Empenhos novos do mesmo grupo voltam à fila como grupo novo; uma regra de
  equivalência de nomes aprovada (futura) poderá absorvê-los com nova versão
  da regra.
