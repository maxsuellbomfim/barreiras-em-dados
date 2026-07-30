# ADR 0003 — Schemas internos e projeções públicas

- Estado: Aceita
- Data: 2026-07-30

## Contexto

No Supabase, tabelas de schemas expostos podem chegar à Data API. O portal
precisa ler somente dados aprovados, enquanto bruto, candidatos e auditoria
devem permanecer internos.

## Decisão

Separar schemas por responsabilidade (`source`, `raw`, domínios, `editorial`,
`evidence`, `audit`). Não criar tabelas de domínio no `public`. O schema `api`
conterá apenas projeções aprovadas e só será exposto após grants e RLS
explícitos. Views usam `security_invoker = true`.

## Consequências

- menor risco de publicação acidental;
- workers recebem grants por schema;
- consultas públicas não dependem de filtros frágeis da aplicação;
- configuração da Data API precisa ser versionada e testada.

## Alternativas

- Tudo em `public` com RLS: rejeitada por superfície e complexidade.
- Filtro `approved` apenas no frontend: rejeitada por risco de bypass.
