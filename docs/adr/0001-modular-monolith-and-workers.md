# ADR 0001 — Monólito modular com workers

- Estado: Aceita
- Data: 2026-07-30

## Contexto

O produto possui vários domínios e fontes, mas a primeira entrega usa apenas um
município e um fluxo de Diário Oficial. Implantar um serviço por pasta aumentaria
operações, segurança e inconsistência transacional antes de haver carga.

## Decisão

Usar um monorepo e um banco PostgreSQL, com limites modulares claros e processos
de worker separados do frontend. Apenas componentes necessários ao fluxo ativo
são implantados. APIs internas FastAPI podem coordenar workers, mas não haverá
chamada síncrona em cascata entre “microsserviços”.

## Consequências

- transações e rastreabilidade são simples;
- módulos podem ser extraídos depois com evidência de carga/ownership;
- falha de um worker não derruba o portal;
- disciplina de imports, schemas e credenciais substitui isolamento de rede
  prematuro.

## Alternativas

- Microsserviços por domínio: rejeitada por custo operacional inicial.
- ETL em rotas Next.js: rejeitada por acoplamento a deploy, timeout e segredo.
