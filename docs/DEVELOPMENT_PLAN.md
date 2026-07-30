# Plano de desenvolvimento — etapa zero

## Objetivo

Entregar uma fundação auditável e um único conector de aquisição, deixando um
handoff seguro para o Claude Code continuar em fatias pequenas.

## Ordem

1. Consolidar documentos e ADRs.
2. Criar estrutura vazia sem instalar aplicações completas.
3. Definir contratos canônicos de coleta, edição, extração e evidência.
4. Gerar migration com a CLI do Supabase e implementar schemas fundamentais.
5. Implementar o conector do Querido Diário sem persistência.
6. Testar paginação, rate limit, retries, circuit breaker e erros explícitos.
7. Fazer revisão de segurança e qualidade de dados.
8. Atualizar inventário de arquivos, limitações e handoff.

## Critérios de conclusão

- escopo e não-escopo não deixam margem para publicação acusatória;
- todos os domínios pedidos aparecem no modelo inicial;
- relações de proveniência são obrigatórias para publicação;
- schemas e migration não dependem de floats monetários;
- conector usa parâmetros da API v0.19.0, código IBGE `2903201` e pagina todas
  as respostas;
- erro HTTP/rede é distinguível de resposta vazia;
- testes offline passam;
- etapa seguinte limitada à preservação de uma janela pequena de edições.

## Delegação sugerida no Claude Code

- `chief-architect`: conferir ADRs e impedir expansão de escopo;
- `data-modeler`: trabalhar somente em `packages/database` e `migrations`;
- `collector-engineer`: trabalhar somente em `workers/collectors`;
- `test-engineer`: fixtures/testes, sem alterar implementação sem tarefa
  separada;
- revisores de segurança, dados e editorial: somente relatório nesta etapa.
