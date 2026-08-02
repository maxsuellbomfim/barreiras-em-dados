# ADR 0015 — RLS nas tabelas internas

- Status: aceito
- Data: 2026-08-02

## Contexto

O portal público consulta projeções e funções do schema `api`. As tabelas de
origem, evidência, normalização, análise, editorial e auditoria não devem ser
uma API pública, mesmo que um privilégio seja concedido acidentalmente no
futuro.

## Decisão

Habilitar Row-Level Security em todas as tabelas internas dos schemas
`source`, `raw`, `org`, `hr`, `procurement`, `finance`, `evidence`, `analysis`,
`editorial` e `audit`. Revogar acesso direto de `public`, `anon` e
`authenticated` e manter as políticas explícitas somente para o papel técnico
`collector_worker`, nas operações já autorizadas pelos grants mínimos.

Tabelas que não precisam ser acessadas pelo coletor ficam sem política de
acesso direto: isso é um bloqueio intencional por padrão. O migration não usa
`FORCE ROW LEVEL SECURITY` globalmente, porque funções `security definer` e
operações do proprietário precisam manter a semântica existente; qualquer
corredor adicional deverá ser criado com política e teste próprios.

## Consequências

- Uma tabela interna não se torna legível por acidente para uma role não
  prevista.
- O coletor mantém somente leitura e inserção/atualização delimitadas pelas
  políticas e pelos grants existentes.
- Projeções públicas continuam sendo a única interface de leitura externa.
- Novos workers precisam declarar grants, política RLS e teste de contrato no
  mesmo change set.
