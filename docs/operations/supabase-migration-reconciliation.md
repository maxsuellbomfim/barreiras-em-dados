# Reconciliação do histórico de migrations do Supabase

## Por que este registro existe

O projeto remoto já tinha migrations aplicadas com identificadores diferentes dos
arquivos que ficaram no checkout local. O `supabase db push --dry-run` interrompia
antes de mostrar as pendências porque encontrava arquivos locais anteriores à
última migration remota.

## Decisão adotada

- Executamos somente `supabase migration fetch --linked`; nenhuma migration foi
  reparada, aplicada ou removida no banco remoto.
- Os arquivos retornados pelo histórico remoto passaram a ser a fonte canônica
  da pasta `supabase/migrations/` para todas as versões já aplicadas.
- As versões locais com o mesmo sufixo funcional foram retiradas da pasta ativa
  e preservadas em `docs/operations/supabase-migrations-legacy/2026-08-04/`.
  O Git mantém o histórico e o conteúdo pode ser recuperado se necessário.
- Três migrations locais de finanças que pareciam pendentes foram comparadas com
  as migrations remotas de automação/reparo. Elas repetiam funções já definidas
  no histórico remoto, portanto também foram preservadas no arquivo legado, em
  vez de serem reaplicadas com novos identificadores.
- As migrations posteriores a `20260804153834` continuam na pasta ativa como
  pendências normais do produto; elas não foram aplicadas automaticamente.
- As cópias posteriores com o mesmo nome funcional das migrations remotas também
  foram movidas para o arquivo legado. Isso evita reaplicar a mesma DDL com outro
  timestamp e mantém apenas as duas mudanças realmente novas no fluxo atual:
  `20260808030000_public_diary_edition_dates.sql` e
  `20260808140000_camara_legislative_author_summary.sql`.
- O `migration fetch` retornou alguns textos históricos com mojibake. Para os
  arquivos que tinham uma contraparte local equivalente, o identificador remoto
  foi mantido, mas o conteúdo UTF-8 legível foi restaurado a partir dessa
  contraparte. Isso não executa novamente a migration; apenas mantém o checkout
  auditável e os contratos de texto testáveis.

## Próxima verificação obrigatória

Antes de qualquer `supabase db push`, execute:

```powershell
pnpm.cmd run supabase migration list
pnpm.cmd run supabase db push --dry-run
```

O dry-run deve listar apenas migrations locais pendentes, sem a mensagem
`LegacyDbPushMissingRemoteError`. A aplicação real continua dependendo de revisão
do PR e de backup/verificação do ambiente.
