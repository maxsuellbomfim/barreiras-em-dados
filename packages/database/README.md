# Database

Migrations, grants, consultas e testes PostgreSQL/Supabase. Tabelas internas não
devem ser criadas no schema `public`.

As migrations são aplicadas em ordem pelo teste PGlite. A migration de
persistência cria `collector_worker` sem login e com grants por coluna. O login
e a senha reais não pertencem ao Git ou à migration: devem ser provisionados no
ambiente e receber somente esse papel.

`raw_artifacts.object_key` não é única porque uma sequência de bytes pode ser
observada mais de uma vez. O objeto físico continua compartilhado por chave
derivada do SHA-256; cada linha preserva a observação, URL, execução e horário.
