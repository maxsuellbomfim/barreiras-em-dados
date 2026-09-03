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

## Reconciliação de 03/09/2026

Seis migrations aplicadas pelo ambiente remoto receberam versões diferentes das
criadas inicialmente no checkout. A comparação SQL mostrou conteúdo funcional
idêntico; o histórico remoto acrescentava somente uma instrução vazia (`;`) ao
final de cada arquivo. Para tornar o diretório ativo novamente compatível com a
tabela de histórico do Supabase:

- `20260902213010` foi substituída pela versão aplicada `20260902213713`;
- `20260902220000` foi substituída pela versão aplicada `20260902220621`;
- `20260902225721` foi substituída pela versão aplicada `20260902230614`;
- `20260902233000` foi substituída pela versão aplicada `20260903013926`;
- `20260903023000` foi substituída pela versão aplicada `20260903020620`;
- `20260903030000` foi substituída pela versão aplicada `20260903021021`.

As versões locais antigas permanecem preservadas em
`docs/operations/supabase-migrations-legacy/2026-09-03/`. Os arquivos canônicos
mantêm o SQL legível já revisado, sem a instrução vazia acrescentada pelo executor.
O teste `supabase-migration-history-reconciliation.test.mjs` exige que cada versão
remota esteja ativa, que a antiga esteja apenas no arquivo legado e que ambas
tenham exatamente o mesmo conteúdo SQL.
