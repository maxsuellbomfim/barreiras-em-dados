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
| Supabase | conectado, cota gratuita esgotada | adaptador opcional |
| Vercel | conectado | somente `apps/web` e `apps/admin` |
| Docker/Podman | não disponível | PostgreSQL em contêiner indisponível |
| Python/Node/pnpm | disponíveis | collectors, testes e monorepo |

Existem dois projetos Supabase conectados, mas pertencem a outros sites. Eles
não serão reutilizados, pausados ou apagados. O projeto gratuito adicional foi
recusado pelo limite da conta; o desenvolvimento segue em modo local portável.
A equipe Vercel conectada ainda não possui projetos.

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

## Etapa 2 — persistência local e futuro provedor

O modo atual usa:

```dotenv
PERSISTENCE_MODE=filesystem
LOCAL_DATA_DIRECTORY=data/local-evidence
```

Ele não exige segredo, preserva objetos e manifestos por SHA-256 e é permitido
somente em `development` e `test`. A pasta `data/` não entra no Git.

Antes de staging, será escolhido um provedor separado para PostgreSQL e
armazenamento privado. Opções gratuitas ou de baixo custo serão avaliadas por:

- compatibilidade real com PostgreSQL e migrations;
- TLS, backups e exportação;
- armazenamento privado compatível com S3 ou adaptável;
- execução de workers fora da Vercel;
- limites, suspensão por inatividade e custo previsível;
- ausência de dependência proprietária no domínio.

### Adaptador Supabase adiado

Nome sugerido: `Barreiras em Dados`.

Região sugerida: `sa-east-1` (São Paulo), pela proximidade dos usuários e das
fontes brasileiras.

Antes da criação:

1. o usuário confirma a organização Supabase;
2. o agente consulta o custo atual;
3. o agente informa o valor;
4. o usuário confirma explicitamente o custo;
5. somente então o projeto é criado.

Se o adaptador for retomado, o projeto recebe:

- migrations versionadas deste repositório;
- bucket privado `raw-artifacts`;
- schema público inicial vazio;
- cadastro público desativado;
- Auth somente por convite para administradores;
- MFA TOTP obrigatório para o painel;
- logs e auditoria;
- login PostgreSQL dedicado para collectors.

## Etapa 3 — chaves e variáveis

### Podem chegar ao navegador

- `NEXT_PUBLIC_SUPABASE_URL`;
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.

A chave publicável identifica o projeto, mas a segurança real continua
dependendo de grants e RLS.

### Somente servidor

- `DATABASE_URL`;
- `SUPABASE_URL`;
- `SUPABASE_SECRET_KEY`;
- credencial restrita do Storage;
- chaves de provedores de IA;
- segredos de e-mail ou alertas.

Nenhuma variável server-side recebe prefixo `NEXT_PUBLIC_`.

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
| PostgreSQL/Auth/Storage | provedor ainda não escolhido |
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
3. Download local de PDF/TXT e preservação como artefato filho.
4. Escolha e ensaio remoto do PostgreSQL/Storage.
5. Health interno de fontes.
6. Esqueleto do admin com Auth, MFA e auditoria.
7. Extração determinística inicial.
8. Um provedor de IA para extração assistiva.
9. Revisão humana.
10. Primeira página pública aprovada.

PNCP, folha, anomalias e múltiplos provedores de IA não começam antes da
estabilização desse primeiro fluxo.
