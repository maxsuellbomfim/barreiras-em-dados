# Guia de configuração e responsabilidades

Este guia foi escrito para que uma pessoa sem experiência em infraestrutura
consiga acompanhar a implantação sem copiar segredos para o código ou conceder
permissões excessivas.

## Regra mais importante

Nunca envie senhas, tokens ou chaves secretas por chat, issue, commit ou
captura de tela.

Quando uma chave for necessária, o responsável pelo projeto a cria no painel do
provedor e a salva diretamente no gerenciador de segredos indicado. O
repositório contém apenas o nome da variável em `.env.example`.

## Estado das conexões em 30/07/2026

| Serviço | Estado | Uso planejado |
|---|---|---|
| Git local | instalado e sincronizado | histórico e commits |
| GitHub CLI | instalado e autenticado | repositório e automações |
| GitHub App | não autorizado | PRs, issues e revisão |
| Supabase | `Barreiras em Dados` ativo | PostgreSQL, Auth e Storage |
| Vercel | conectado | somente `apps/web` e `apps/admin` |
| Docker/Podman | não disponível | PostgreSQL em contêiner indisponível |
| Python/Node/pnpm | disponíveis | collectors, testes e monorepo |

O projeto `Site Kelvin Vinicius` foi pausado, não apagado, para liberar a cota.
O projeto `Maxsuell Bomfim | Defesa em Saúde` continua ativo e intocado. O novo
`Barreiras em Dados` está `ACTIVE_HEALTHY` em São Paulo. O desenvolvimento local
continua portável e não depende de credenciais do Supabase.

## Etapa 1 — GitHub concluído

O repositório privado é
<https://github.com/maxsuellbomfim/barreiras-em-dados>, com branch `main`.

Responsabilidade do usuário:

1. autorizar a instalação do GitHub CLI;
2. concluir o login do GitHub no navegador quando solicitado;
3. ativar MFA na conta GitHub, se ainda não estiver ativo.

Responsabilidade do agente:

1. conferir novamente arquivos ignorados e ausência de segredos;
2. inicializar Git com branch `main`;
3. criar o repositório privado;
4. criar o primeiro commit;
5. enviar `main` ao GitHub;
6. ativar proteções possíveis e documentar as restantes.

Os ZIPs de inspiração, `.venv`, `node_modules`, `.env` e artefatos coletados
ficam apenas no computador e estão ignorados.

## Etapa 2 — persistência local e Supabase isolado

O modo atual usa:

```dotenv
PERSISTENCE_MODE=filesystem
LOCAL_DATA_DIRECTORY=data/local-evidence
```

Ele não exige segredo, preserva objetos e manifestos por SHA-256 e é permitido
somente em `development` e `test`. A pasta `data/` não entra no Git.

O domínio continua independente do provedor. Uma substituição futura deverá ser
avaliada por:

- compatibilidade real com PostgreSQL e migrations;
- TLS, backups e exportação;
- armazenamento privado compatível com S3 ou adaptável;
- execução de workers fora da Vercel;
- limites, suspensão por inatividade e custo previsível;
- ausência de dependência proprietária no domínio.

### Projeto Supabase provisionado

Nome: `Barreiras em Dados`.

Project ref: `mpladsyzilmgiefejpkq`.

Região: `sa-east-1` (São Paulo).

Estado verificado: `ACTIVE_HEALTHY`.

Configurações aplicadas em 30/07/2026:

- 5 migrations versionadas e registradas no histórico remoto;
- 40 tabelas internas e nenhuma tabela no schema `public`;
- 3 fontes e 3 endpoints iniciais;
- bucket `raw-artifacts` privado, limitado a 100 MB por objeto e com allowlist
  de MIME;
- role-base `collector_worker` sem login, sem `DELETE` ou `UPDATE` no bruto;
- role `collector_querido_diario` sem LOGIN, membro de `collector_worker` e
  limitada a 2 conexões;
- políticas do Storage para `SELECT` e `INSERT` apenas no prefixo
  `querido-diario/gazettes/`, vinculadas a UUID Auth autorizado;
- extensão `pg_trgm` isolada em `extensions`;
- 123 chaves estrangeiras com índice de cobertura;
- advisors sem alerta de segurança.

Configurações ainda pendentes:

- cadastro público desativado;
- Auth somente por convite para administradores;
- MFA TOTP obrigatório para o painel;
- criação do usuário Auth técnico e registro do seu UUID na allowlist;
- ativação de LOGIN e senha da role `collector_querido_diario` por canal
  interativo seguro;
- teste negativo usando a identidade real do workload;
- política operacional de logs, backup e rotação.

O procedimento sem compartilhamento de senhas está em
[`COLLECTOR_CREDENTIALS.md`](COLLECTOR_CREDENTIALS.md).

## Etapa 3 — chaves e variáveis

### Podem chegar ao navegador

- `NEXT_PUBLIC_SUPABASE_URL`;
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.

A chave publicável identifica o projeto, mas a segurança real continua
dependendo de grants e RLS.

### Somente servidor

- `DATABASE_URL`;
- `SUPABASE_URL`;
- `SUPABASE_WORKLOAD_EMAIL`;
- `SUPABASE_WORKLOAD_PASSWORD`;
- chaves de provedores de IA;
- segredos de e-mail ou alertas.

Nenhuma variável server-side recebe prefixo `NEXT_PUBLIC_`.

O coletor usa `SUPABASE_PUBLISHABLE_KEY` junto da sessão do usuário Auth
técnico. Ele recusa `SUPABASE_SECRET_KEY` e `SUPABASE_SERVICE_ROLE_KEY`, pois
essas chaves ignoram RLS. A chave publicável pode ser conhecida pelo cliente; a
senha do workload e a senha PostgreSQL nunca são enviadas ao repositório ou ao
chat.

No Vercel, segredos de Preview e Production devem ser marcados como
**Sensitive**. Collectors não usam segredos do Vercel; usam o ambiente do worker
ou GitHub Actions.

## Etapa 4 — painel administrativo

O primeiro painel admin terá somente:

1. login por convite;
2. cadastro obrigatório de MFA;
3. lista de execuções e saúde das fontes;
4. fila de extrações candidatas;
5. documento e trecho lado a lado;
6. aprovar, rejeitar ou solicitar correção;
7. motivo obrigatório;
8. histórico append-only de decisões.

Papéis iniciais:

- `reviewer`: revisa e corrige campos;
- `publisher`: publica um registro já revisado;
- `admin`: convida usuários e gerencia papéis;
- `auditor`: somente leitura.

Uma pessoa não deve extrair, revisar e publicar sozinha um caso sensível. Papéis
ficam em `app_metadata`, nunca em `user_metadata`.

## Etapa 5 — APIs de IA

Não é necessário contratar vários provedores no início. A recomendação é:

1. começar com um provedor;
2. usar uma interface interna independente do provedor;
3. enviar apenas o trecho necessário, nunca o banco inteiro;
4. registrar provedor, modelo, prompt, horário e custo;
5. validar a resposta com schema;
6. manter resultado como candidato;
7. exigir revisão humana para publicar;
8. nunca usar IA para total financeiro.

Variáveis sugeridas:

- `AI_PROVIDER`;
- `OPENAI_API_KEY`, se OpenAI estiver habilitada;
- `ANTHROPIC_API_KEY`, se Anthropic estiver habilitada;
- `GOOGLE_GENERATIVE_AI_API_KEY`, se Google estiver habilitada;
- `AI_MODEL_EXTRACTION`;
- `AI_MAX_COST_PER_RUN`.

Somente a chave do provedor realmente usado deve existir no ambiente. As chaves
serão criadas pelo usuário no painel oficial e inseridas diretamente no
gerenciador de segredos; não serão entregues ao agente por mensagem.

## Onde cada parte será executada

| Parte | Ambiente inicial |
|---|---|
| Portal público Next.js | Vercel |
| Painel admin Next.js | Vercel |
| PostgreSQL/Auth/Storage | Supabase isolado |
| Evidência de desenvolvimento | filesystem local append-only |
| Collectors Python agendados | GitHub Actions, provisoriamente |
| Filas | PostgreSQL |
| Processamento de documentos | worker Python |
| IA assistiva | worker/server, nunca browser |

GitHub Actions serve como solução provisória para coletas agendadas de baixo
volume. Um runtime próprio de workers será escolhido quando duração, volume ou
isolamento exigirem.

## Ordem de implantação

1. GitHub privado e primeiro commit — concluído.
2. Acervo local imutável e replay de uma coleta de um dia — concluído.
3. Aplicar migrations/seed e revisar advisors no Supabase — concluído.
4. Provisionar a identidade do coletor e restringi-la ao banco e ao
   bucket/prefixo — limites aplicados; ativação segura pendente.
5. Download local de PDF/TXT e preservação como artefato filho.
6. Health interno de fontes.
7. Esqueleto do admin com Auth, MFA e auditoria.
8. Extração determinística inicial.
9. Um provedor de IA para extração assistiva.
10. Revisão humana e primeira página pública aprovada.

PNCP, folha, anomalias e múltiplos provedores de IA não começam antes da
estabilização desse primeiro fluxo.
