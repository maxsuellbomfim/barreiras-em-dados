# Instruções do projeto — Barreiras em Dados

## Missão

Construir uma plataforma municipal apartidária, verificável e compreensível.
O código deve preservar a cadeia de custódia dos dados e nunca converter sinais
estatísticos em acusações.

## Ordem obrigatória de trabalho

1. Leia os documentos em `docs/` e os ADRs aplicáveis.
2. Confirme o menor fluxo vertical em andamento.
3. Faça mudanças somente no módulo delegado.
4. Execute testes proporcionais ao risco.
5. Revise segurança, qualidade de dados e documentação.
6. Informe limitações e não inicie uma nova fase grande automaticamente.

## Etapa ativa

A etapa ativa é **1B — documento e extração candidata**. A etapa 1A foi
encerrada em 31/07/2026 com validação em produção: o workflow diário coleta as
páginas JSON e preserva PDF/texto de cada edição como artefatos filhos
verificados por SHA-256, com limites de tamanho e quantidade, content-type
normalizado por papel e validação de corpo (`%PDF-`). O replay é idempotente e
o caminho de falha foi exercitado de verdade (execução nº 4 falhou explícita e
sanitizada; a nº 5 replayou completa). O status público agregado está no ar em
`barreiras-em-dados.vercel.app` sem expor o esquema interno, e a visão interna
`source.querido_diario_daily_coverage` mostra lacunas por dia sem acesso
anônimo. Revisões em `docs/reviews/STAGE_1A_*.md`.

O projeto Supabase isolado `Barreiras em Dados` segue em São Paulo com advisor
limpo, exceto o aviso conhecido de proteção contra senhas vazadas do plano
gratuito — que também não oferece backup automático; a mitigação registrada é
o bruto re-coletável endereçado por hash e migrations/seed reproduzíveis. A
role `collector_querido_diario` mantém LOGIN, duas conexões e nenhum privilégio
administrativo. O UUID Auth técnico ativo é
`1575c740-fcff-4b1a-89a9-e8e5a314880a`, autorizado exclusivamente no bucket
`raw-artifacts`, prefixo `querido-diario/gazettes/`, para `SELECT` e `INSERT`.
As credenciais técnicas vivem somente no GitHub Actions.

A menor fatia de 1B está implementada: texto canônico das edições preservadas
e candidatos determinísticos de nomeação/exoneração em fila `needs_review`,
sem publicação e sem LLM, como passo do workflow diário. Um segundo
agendamento faz backfill retroativo automático, quatro vezes ao dia, de uma
janela curta por execução derivada do banco, até
`QUERIDO_DIARIO_BACKFILL_HORIZON` (2021-01-01, gestão anterior incluída). O
gate atual é validar remotamente a extração e o backfill; depois, extração de
campos (pessoa, cargo, datas) com incerteza por campo. Parser além disso e
PNCP continuam fora de escopo. O projeto `Site Kelvin Vinicius` foi pausado,
não apagado, para liberar a cota; não o reutilize nem altere os demais
projetos.

## Regras inegociáveis

- Todo registro normalizado deve apontar para ao menos um `raw_record` ou
  `raw_artifact` por meio de `evidence_items`.
- Artefatos brutos são append-only e endereçados por SHA-256.
- Falha de fonte não é “zero resultados”; use estados explícitos de execução.
- Valores monetários usam decimal exato (`numeric` no PostgreSQL), nunca float.
- Cálculos financeiros e regras de anomalia são determinísticos e versionados.
- LLMs não calculam totais e não publicam conteúdo automaticamente.
- Fato, inferência, anomalia e hipótese devem ser campos/estados distintos.
- Nenhum achado reputacional é publicado sem revisão humana registrada.
- Não publicar CPF completo, descontos pessoais ou dados sensíveis
  desnecessários.
- Correções criam novas versões; histórico não é alterado ou apagado em
  silêncio.
- Não colocar chaves administrativas em código cliente ou variáveis
  `NEXT_PUBLIC_*`.
- Coletores não vivem em rotas Next.js nem dependem do ciclo de deploy web.

## Limites modulares

- `workers/collectors`: aquisição externa e emissão de registros brutos.
- `workers/document-processing`: OCR, páginas e trechos.
- `workers/normalization`: transformação tipada, sem publicação.
- `workers/reconciliation`: identidades e conflitos entre fontes.
- `workers/anomaly-detection`: regras determinísticas e achados não editoriais.
- `packages/database`: migrations, acesso e transações.
- `packages/data-contracts`: schemas canônicos.
- `packages/evidence`: cadeia de evidências e hashes.
- `apps/admin`: revisão humana; nunca é fonte de fatos.
- `apps/web` e `apps/public-api`: somente dados aprovados.

Agentes com permissão de escrita devem receber um único limite modular por
tarefa. Revisores não devem corrigir silenciosamente o que encontrarem.

## Referências externas na raiz

Os ZIPs são apenas inspiração:

- `honestidade-politicos-brasil-main.zip`;
- `Poligrafo-main.zip`;
- `transparencia-politica-2026-main.zip`.

Não extraia os ZIPs na raiz e não copie código sem registrar licença e
atribuição em `THIRD_PARTY_NOTICES.md`. Prefira reimplementação adequada ao
escopo municipal.
