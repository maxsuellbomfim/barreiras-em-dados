# Estratégia de ferramentas

## Adicionar na fundação

| Área | Ferramentas sugeridas | Uso |
|---|---|---|
| Monorepo web | pnpm e Turborepo | dependências, tarefas e cache por pacote |
| Python | uv, Ruff, mypy, pytest e Hypothesis | lockfile, lint, tipos e testes |
| HTTP | httpx e respx | transporte assíncrono e testes isolados |
| Contratos | Pydantic e JSON Schema 2020-12 | validar fronteiras e fixtures |
| Banco | PostgreSQL, pgTAP, SQLFluff e CLI do provedor | migrations e lint SQL |
| Web | Playwright e axe-core | fluxos e acessibilidade |
| Segurança | Gitleaks, Semgrep, OSV-Scanner e pip-audit | segredos, SAST e dependências |
| Observabilidade | OpenTelemetry e logs JSON | traces de coleta a publicação |

Dependências devem ser fixadas em lockfiles. Actions de terceiros devem usar
commit SHA e permissões mínimas.

## Adicionar quando o fluxo exigir

- `pdfplumber`/`pypdf` para texto e metadados de PDFs;
- OCRmyPDF e Tesseract para documentos sem camada de texto;
- ClamAV e processamento isolado, sem JavaScript, macros ou acesso de rede,
  antes de manipular documentos;
- Storybook e Lighthouse CI quando o sistema visual começar;
- Sentry somente com remoção de conteúdo documental e dados pessoais;
- Postgres full-text search e `pg_trgm` antes de avaliar outro buscador;
- Supabase Queues/PGMQ apenas se a fila SQL simples deixar de atender.

## Integrações úteis para o Claude Code

- GitHub para issues, pull requests e CI;
- provedor PostgreSQL/Storage em projeto isolado, com acesso restrito e sem
  credencial administrativa de produção;
- navegador/Playwright para validar interfaces;
- documentação oficial de Querido Diário, PNCP, SICONFI, PostgreSQL e do
  provedor escolhido.

Agentes recebem apenas ferramentas necessárias ao módulo delegado. Revisores
jurídico-editorial e de fontes continuam somente leitura.

## Evitar por enquanto

- Kafka, Kubernetes e orquestradores distribuídos;
- Elasticsearch/OpenSearch antes de medir limites do PostgreSQL;
- banco vetorial ou grafo sem caso de uso comprovado;
- ML para anomalias antes de regras determinísticas básicas;
- chatbot público antes de existir uma camada de evidência confiável;
- múltiplos serviços web independentes para domínios que ainda mudam juntos.
