# Revisão de encerramento da etapa 1A

Data: 31/07/2026.

## Resultado

A etapa 1A — coleta preservada do Diário — está encerrada. O acervo em
produção contém, para 10/06/2026: uma página JSON preservada, duas edições
distintas e quatro documentos filhos (dois textos, dois PDFs, 19,7 MB)
verificados por SHA-256, todos ligados à página de origem por
`parent_artifact_id`.

## Itens do gate e evidências

- **Replay sem duplicação**: execuções nº 2/3/5 do workflow reutilizaram
  página, execução e registros existentes sem criar duplicatas; testes de
  idempotência locais cobrem página, documento e manifesto.
- **Modo local restrito e adulteração detectável**: persistência filesystem
  exige `APP_ENV` development/test; manifestos são verificados por hash do
  próprio arquivo e bytes divergentes sob a mesma chave são recusados.
- **429/5xx/timeout/circuit breaker/DLQ**: cobertos por testes unitários; o
  caminho integrado foi exercitado em produção sem simulação — a execução
  nº 4 falhou pelo MIME recusado, não gravou nada parcial, registrou DLQ
  sanitizada, e a nº 5 completou a mesma janela após a correção.
- **Lacunas e última coleta visíveis**: última coleta e cobertura no status
  público; lacunas por dia na visão interna
  `source.querido_diario_daily_coverage` (sem acesso anon/authenticated;
  janelas de coleta passam a ser registradas por execução a partir desta
  entrega).
- **Restauração por hash**: cada persistência relê o objeto do Storage e
  confere SHA-256 e tamanho antes do registro transacional.
- **Bucket, grants e backup**: bucket privado com MIME allowlist e limite de
  100 MB; RLS por prefixo único; grants por coluna sem DELETE/UPDATE no bruto.
  O plano gratuito do Supabase não oferece backup automático nem PITR.
  Decisão registrada: aceitável nesta fase porque o bruto é re-coletável da
  fonte com verificação por hash, os objetos são imutáveis e endereçados por
  conteúdo, e migrations/seed são reproduzíveis a partir do repositório.
  Antes de staging, contratar backup do provedor ou export agendado.

## Limitações conhecidas

- As execuções anteriores a esta entrega não têm janela registrada e aparecem
  na visão de lacunas como não atribuíveis.
- A cobertura histórica é uma amostra-piloto de um dia; o backfill gradual
  ocorrerá pelas janelas diárias e por disparos manuais de até sete dias.

## Próxima etapa

1B — derivar texto canônico das edições preservadas e identificar candidatos
determinísticos de nomeação/exoneração em fila interna, sem publicação. A fila
será consumida pelo portal admin (etapa 1C), onde cada candidato exibirá o
trecho de evidência e exigirá aprovação humana registrada antes de qualquer
publicação.
