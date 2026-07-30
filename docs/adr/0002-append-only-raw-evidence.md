# ADR 0002 — Camada bruta append-only por hash

- Estado: Aceita
- Data: 2026-07-30

## Contexto

URLs e respostas oficiais mudam. Sem cópia preservada, uma extração não pode ser
reproduzida nem auditada.

## Decisão

Preservar respostas e documentos antes de transformá-los. Conteúdo é endereçado
por SHA-256, com metadados de coleta no PostgreSQL e bytes em bucket privado.
Artefatos brutos, registros brutos e eventos de auditoria são append-only para
roles da aplicação. Correções e novos parsers geram novas versões.

## Consequências

- deduplicação por conteúdo sem perder ocorrências;
- replay e auditoria reprodutíveis;
- custo de armazenamento e política de retenção precisam ser monitorados;
- acesso público ao original depende de classificação editorial, não do bucket
  bruto.

## Alternativas

- Guardar apenas URL: rejeitada porque não preserva versão.
- Sobrescrever arquivo por edição: rejeitada porque apaga mudança da fonte.
