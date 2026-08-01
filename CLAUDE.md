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

As etapas ativas são **1B/1C — extração candidata com revisão e publicação**
e o início da **Etapa 2 — PNCP**. A 1A foi encerrada em 31/07/2026 com
validação em produção (replay idempotente, artefatos filhos verificados por
SHA-256, caminho de falha exercitado de verdade; status público agregado em
`barreiras-em-dados.vercel.app`; revisões em `docs/reviews/STAGE_1A_*.md`).
O Querido Diário está parado em 10/06/2026 porque a prefeitura migrou o
diário de plataforma; a fonte primária agora é o coletor direto por cursor
de edição (`barreiras.ba.gov.br/diario/pdf/<ano>/diario<edição>.pdf`), com
o QD mantido como backfill e verificação cruzada
(`docs/reviews/STAGE_1B_DIRECT_DIARY_DISCOVERY.md`).

O projeto Supabase isolado `Barreiras em Dados` segue em São Paulo com advisor
limpo, exceto o aviso conhecido de proteção contra senhas vazadas do plano
gratuito — que também não oferece backup automático; a mitigação registrada é
o bruto re-coletável endereçado por hash e migrations/seed reproduzíveis. A
role `collector_querido_diario` mantém LOGIN, duas conexões e nenhum privilégio
administrativo. O UUID Auth técnico ativo é
`1575c740-fcff-4b1a-89a9-e8e5a314880a`, autorizado exclusivamente no bucket
`raw-artifacts`, prefixos `querido-diario/gazettes/`,
`barreiras-diario/gazettes/` e `pncp/procurement/`, para `SELECT` e `INSERT`
(`audit.storage_workload_identities`). As credenciais técnicas — incluindo as
chaves da cascata de IA (Groq, OpenRouter, Gemini) — vivem somente no GitHub
Actions.

A 1B tem texto canônico (embutido e OCR Tesseract para páginas escaneadas),
candidatos determinísticos e campos com estado explícito (pessoa, cargo,
símbolo, órgão, número e data da Portaria) rodando como passos do workflow
diário, e backfill retroativo automático quatro vezes ao dia até
`QUERIDO_DIARIO_BACKFILL_HORIZON` (2021-01-01). A 1C tem fila de revisão
autenticada em `apps/admin` (revisores em `audit.reviewer_identities`;
primeiro revisor ativo em 01/08/2026), decisão aprovar/rejeitar com
justificativa, retirada e histórico auditados em
`editorial.editorial_reviews`, e projeção pública somente de aprovados em
`/atos` — cada ato publicado leva um resumo assistido (cascata de IA, ADR
0011) revisado por humano: nada é publicado sem explicação simples. MFA foi
adiado por decisão do titular e é obrigatório antes do lançamento divulgado.
A Etapa 2 coleta do PNCP: cadastro semanal por CNPJ, contratações das 13
modalidades com paginação completa, backfill diário até 2021-07-01 e itens e
resultados homologados derivados do banco.

O gate atual é validar os agendamentos remotos (coleta direta, OCR, cascata
de IA, backfills e a primeira janela PNCP — a API de consulta estava
degradada na fonte em 01/08/2026) e revisar os primeiros candidatos reais.
Amostra anotada com especialista segue pendente. O projeto
`Site Kelvin Vinicius` foi pausado, não apagado, para liberar a cota; não o
reutilize nem altere os demais projetos.

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
