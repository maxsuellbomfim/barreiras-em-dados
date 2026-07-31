# Database

Migrations, grants, consultas e testes PostgreSQL/Supabase. Tabelas internas não
devem ser criadas no schema `public`.

As migrations são aplicadas em ordem pelo teste PGlite. A fundação cria
`collector_worker` sem login e com grants por coluna. A role
`collector_querido_diario` também nasce sem LOGIN, recebe somente esse papel e
fica limitada a duas conexões. A senha real não pertence ao Git nem à migration:
deve ser ativada por prompt interativo seguro.

O Storage usa `audit.storage_workload_identities` como allowlist interna de UUID,
bucket e prefixo. A função de autorização consulta `auth.uid()` e as policies
permitem somente `SELECT`/`INSERT`; acesso direto à allowlist, `UPDATE` e
`DELETE` permanecem negados.

`raw_artifacts.object_key` não é única porque uma sequência de bytes pode ser
observada mais de uma vez. O objeto físico continua compartilhado por chave
derivada do SHA-256; cada linha preserva a observação, URL, execução e horário.
