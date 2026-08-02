# 0016 — Corredor de evidência bruta da transparência municipal

Data: 2026-08-02. Status: proposta, aguardando revisão e merge.

## Contexto

O conector municipal já valida HTTPS, host oficial, paginação, limites,
retries, circuit breaker e hash da resposta. A persistência raw-first também
está implementada, mas o prefixo `municipal-transparency/` ainda não pode ser
usado pelo Storage privado. A lista de corredores deve permanecer fechada para
que uma credencial de coleta não consiga escrever em outra fonte.

## Decisão

Adicionar `municipal-transparency/` à constraint de corredores permitidos,
preservando os sete prefixos já ativos. Esta alteração é somente de capacidade:

- nenhuma identidade Auth é criada ou ativada;
- nenhuma senha, token ou service role é incluída;
- nenhum objeto é escrito no Storage;
- o coletor continua sem acesso até existir uma linha ativa em
  `audit.storage_workload_identities` vinculada a um UUID técnico específico;
- a identidade municipal deverá usar o bucket privado `raw-artifacts`,
  `SELECT` e `INSERT`, sem `UPDATE`, `DELETE` ou `upsert`.

## Consequências

O próximo passo operacional exige revisão humana, criação de uma credencial
técnica separada e registro auditável do UUID. Até lá, a aplicação não publica
valores de receita e não faz normalização financeira. A migration pode ser
aplicada sem alterar dados existentes e pode ser auditada pelo catálogo de
constraints.
