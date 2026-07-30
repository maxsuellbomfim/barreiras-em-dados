# ADR 0004 — JSON Schema como contrato canônico

- Estado: Aceita
- Data: 2026-07-30

## Contexto

Next.js/TypeScript e workers Python precisam compartilhar semântica e validar
fixtures sem duplicar manualmente contratos incompatíveis.

## Decisão

Manter JSON Schema 2020-12 versionado em `packages/data-contracts/schemas`.
Tipos TypeScript e modelos Python serão gerados ou adaptados a partir desses
schemas. Toda mensagem inclui `schema_name` e `schema_version`.

## Consequências

- fixtures e eventos podem ser validados independentemente da linguagem;
- mudança incompatível exige nova versão;
- geração de código entra no CI;
- regras de domínio continuam também no banco, não apenas no schema.

## Alternativas

- TypeScript como fonte única: rejeitada por acoplamento dos workers.
- Pydantic como fonte única: rejeitada pelo mesmo motivo.
- Protobuf agora: rejeitada por complexidade e baixa necessidade.
