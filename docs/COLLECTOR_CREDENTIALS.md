# Ativação segura das credenciais do coletor

Este procedimento ativa o primeiro workload sem enviar senha ao chat, Git ou
histórico de comandos. Ele se aplica somente ao projeto Supabase
`Barreiras em Dados` (`mpladsyzilmgiefejpkq`).

## Estado seguro inicial

- `collector_worker`: papel-base sem login;
- `collector_querido_diario`: identidade PostgreSQL sem LOGIN;
- limite da identidade PostgreSQL: 2 conexões;
- bucket `raw-artifacts`: privado;
- usuário Auth técnico: ainda não criado;
- allowlist do Storage: vazia;
- políticas: somente `SELECT` e `INSERT` para UUID ativo no prefixo
  `querido-diario/gazettes/`;
- `UPDATE`, `DELETE`, outro bucket e outro prefixo: negados;
- secret/service role: recusada pelo coletor.

Enquanto as duas credenciais não forem ativadas, nenhuma coleta remota pode
escrever.

## Parte 1 — ação do responsável no painel Supabase

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

## Parte 2 — ação do agente depois de receber o UUID

O agente deverá:

1. confirmar que o UUID existe em `auth.users`;
2. cadastrar o UUID em `audit.storage_workload_identities`;
3. limitar o registro a `raw-artifacts/querido-diario/gazettes/`;
4. ativar somente `SELECT` e `INSERT`;
5. testar usuário não cadastrado, outro bucket, outro prefixo, `UPDATE` e
   `DELETE`;
6. executar novamente os advisors de segurança.

## Parte 3 — senha PostgreSQL por prompt interativo

A senha PostgreSQL não deve ser escrita no SQL Editor, porque pode aparecer no
histórico. O caminho preferido é o cliente `psql`:

1. instalar somente o cliente PostgreSQL;
2. no Dashboard, clicar em **Connect** e copiar a conexão de **Session pooler**;
3. conectar como administrador usando a senha do banco guardada pelo
   responsável;
4. executar:

```psql
ALTER ROLE collector_querido_diario LOGIN;
\password collector_querido_diario
```

O comando `\password` solicita a nova senha sem exibi-la. Gere outra senha única
de pelo menos 24 caracteres e salve-a como
`Barreiras em Dados — PostgreSQL — Querido Diário`.

Na conexão pelo pooler, o usuário normalmente recebe o sufixo do projeto:

```text
collector_querido_diario.mpladsyzilmgiefejpkq
```

Copie o formato exato mostrado pelo Dashboard e mantenha
`sslmode=require` ou `verify-full`.

Se a senha administrativa do banco não estiver disponível, pare. A redefinição
dessa senha exige autorização específica e deve ocorrer antes de existir
qualquer integração dependente dela.

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

1. login PostgreSQL conecta com TLS;
2. login pode inserir as colunas autorizadas;
3. login não pode alterar nem apagar `raw_artifacts`/`raw_records`;
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
