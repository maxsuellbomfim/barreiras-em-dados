# Ativação segura das credenciais do coletor

Este procedimento ativa o primeiro workload sem enviar senha ao chat, Git ou
histórico de comandos. Ele se aplica somente ao projeto Supabase
`Barreiras em Dados` (`mpladsyzilmgiefejpkq`).

## Estado em 30/07/2026

- `collector_worker`: papel-base sem login;
- `collector_querido_diario`: identidade PostgreSQL com LOGIN ativo;
- limite da identidade PostgreSQL: 2 conexões;
- bucket `raw-artifacts`: privado;
- usuário Auth técnico: criado, confirmado e não anônimo;
- User UID autorizado: `d3e7a733-6101-4c9e-8d7a-d0f88a243eee`;
- allowlist do Storage: uma identidade ativa para o Querido Diário;
- políticas: somente `SELECT` e `INSERT` para UUID ativo no prefixo
  `querido-diario/gazettes/`;
- `UPDATE`, `DELETE`, outro bucket e outro prefixo: negados;
- secret/service role: recusada pelo coletor.

As duas identidades estão ativadas. A identidade PostgreSQL real já foi testada.
Nenhuma coleta remota completa deve ser executada antes do teste da identidade
Auth real no Storage e do replay idempotente.

## Parte 1 — ação do responsável no painel Supabase (concluída)

1. Abra o
   [projeto Barreiras em Dados](https://supabase.com/dashboard/project/mpladsyzilmgiefejpkq).
2. Entre em **Authentication → Users**.
3. Clique em **Add user**.
4. Prefira **Create new user**. Se o painel oferecer somente convite, use
   **Send invitation** e conclua o convite na caixa postal técnica.
5. Use um e-mail técnico controlado pelo responsável, não a conta pessoal de
   administração. Um alias de uma caixa já protegida é suficiente nesta etapa.
6. No gerenciador de senhas, gere uma senha única com pelo menos 24 caracteres.
7. Salve o e-mail e a senha no gerenciador sob o nome
   `Barreiras em Dados — Storage — Querido Diário`.
8. Se estiver criando diretamente, marque **Auto Confirm User**.
9. Abra o usuário criado e copie o campo **User UID**.

Envie ao agente **somente o User UID**. UUID não é senha. Não envie e-mail,
senha, token, captura de tela com credenciais nem chave secreta.

## Parte 2 — ativação do UUID pelo agente (concluída)

O UUID informado foi validado em `auth.users` sem expor e-mail ou senha e
registrado de forma auditável em `audit.storage_workload_identities`.

Resultado verificado:

- `SELECT` e `INSERT` permitidos somente em
  `raw-artifacts/querido-diario/gazettes/`;
- `UPDATE`, `DELETE`, outro bucket e outro prefixo negados;
- UUID não cadastrado sem acesso;
- um evento append-only de ativação registrado em `audit.audit_events`;
- role PostgreSQL `collector_querido_diario` ainda estava com `NOLOGIN` nesta
  parte do procedimento;
- advisor sem alerta de RLS ou exposição de dados;
- aviso do Auth: proteção contra senhas vazadas desativada.

O aviso do Auth pode ser mitigado usando senha aleatória, exclusiva e longa,
guardada no gerenciador de senhas. A ativação do recurso nativo deverá ser
avaliada no painel, inclusive quanto à disponibilidade no plano gratuito.

## Parte 3 — senha PostgreSQL por prompt interativo (concluída)

A senha PostgreSQL não deve ser escrita no SQL Editor, porque pode aparecer no
histórico. O caminho preferido é o cliente `psql`:

1. instalar somente o cliente PostgreSQL — concluído;
2. no Dashboard, clicar em **Connect** e copiar a conexão de **Session pooler**;
3. conectar como administrador usando a senha do banco guardada pelo
   responsável — concluído;
4. definir a senha enquanto a role ainda estava bloqueada e só depois ativar o
   LOGIN — concluído:

```psql
BEGIN;
\password collector_querido_diario
ALTER ROLE collector_querido_diario LOGIN CONNECTION LIMIT 2;
COMMIT;
```

O comando `\password` solicita a nova senha sem exibi-la. Gere outra senha única
de pelo menos 24 caracteres e salve-a como
`Barreiras em Dados — PostgreSQL — Querido Diário`.

### Cliente local verificado

- versão: `psql (PostgreSQL) 17.10`;
- origem: ZIP Windows x64 apontado pela página oficial do PostgreSQL/EDB;
- instalação: `%LOCALAPPDATA%\Programs\PostgreSQL\17-client`;
- PATH do usuário: configurado;
- `postgres.exe`: ausente;
- serviço PostgreSQL local: ausente;
- ZIP temporário: removido;
- SHA-256 do ZIP:
  `ef9b1e5e23d2e8a83914ba13d9dc536a72210fba53fd1808ff1f7e06bb22b106`.
- certificado TLS: `Supabase Root 2021 CA`, válido até 26/04/2031;
- SHA-256 do certificado:
  `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`.

O `psql.exe` do arquivo ZIP não possui assinatura Authenticode. A proveniência
foi limitada ao link HTTPS apresentado pela página oficial e ao hash registrado.
Não reutilizar outro arquivo com o mesmo nome sem uma nova verificação.

Na conexão pelo pooler, o usuário normalmente recebe o sufixo do projeto:

```text
collector_querido_diario.mpladsyzilmgiefejpkq
```

Copie o formato exato mostrado pelo Dashboard e mantenha
`sslmode=require` ou `verify-full`.

Se a senha administrativa do banco não estiver disponível, pare. A redefinição
dessa senha exige autorização específica e deve ocorrer antes de existir
qualquer integração dependente dela.

O acesso temporário documentado pelo Supabase não apareceu no painel deste
projeto. Com autorização expressa, a senha administrativa foi redefinida antes
de existir integração dependente dela e guardada fora do chat e do Git.

### Resultado remoto

- `collector_querido_diario`: `LOGIN`, limite de 2 conexões;
- membro de `collector_worker`;
- sem superusuário, criação de role/banco, replicação ou `BYPASSRLS`;
- login real aprovado pelo Session pooler com TLS `verify-full`;
- `current_user` confirmado como `collector_querido_diario`;
- inserção temporária em `source.collection_runs` aprovada e revertida;
- tentativas reais de `DELETE` em `raw.raw_artifacts` e `UPDATE` em
  `raw.raw_records` negadas;
- zero registros `credential-smoke-test` permaneceram após o rollback;
- sem `DELETE` em `raw.raw_artifacts`;
- sem `UPDATE` em `raw.raw_records`;
- um evento append-only `database_workload_identity.activated`;
- senha administrativa e senha do coletor não foram observadas pelo agente.

## Parte 4 — variáveis do worker

Somente em ambiente local ignorado pelo Git ou no gerenciador de segredos do
runtime:

```dotenv
PERSISTENCE_MODE=postgres-supabase
DATABASE_URL=
SUPABASE_URL=https://mpladsyzilmgiefejpkq.supabase.co
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_WORKLOAD_EMAIL=
SUPABASE_WORKLOAD_PASSWORD=
SUPABASE_RAW_ARTIFACTS_BUCKET=raw-artifacts
```

`SUPABASE_PUBLISHABLE_KEY` é obtida em **Project Settings → API Keys**. Não use
`sb_secret_*`, `service_role` ou a senha administrativa do banco no worker.

## Parte 5 — testes antes da primeira coleta

1. [concluído] login PostgreSQL conecta com TLS `verify-full`;
2. [concluído] login pode inserir as colunas autorizadas;
3. [concluído] login não pode alterar nem apagar
   `raw_artifacts`/`raw_records`;
4. usuário Auth pode criar e restaurar objeto no prefixo permitido;
5. usuário Auth não pode escrever em `pncp/` ou outro bucket;
6. usuário Auth não pode atualizar nem apagar objeto;
7. uma janela de um dia é coletada;
8. o mesmo comando é repetido sem duplicação;
9. o objeto é restaurado e o SHA-256 é comparado.

## Revogação

Em incidente ou troca de responsável, nesta ordem:

1. mudar a allowlist para `suspended`;
2. executar `ALTER ROLE collector_querido_diario NOLOGIN`;
3. revogar as sessões do usuário Auth;
4. rotacionar as duas senhas;
5. registrar o evento em auditoria;
6. só então reativar e repetir os testes negativos.
