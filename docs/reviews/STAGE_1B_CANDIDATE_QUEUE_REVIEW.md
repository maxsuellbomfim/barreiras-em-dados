# Revisão da etapa 1B — fatia inicial: texto canônico e fila de candidatos

Data: 31/07/2026.

## Escopo

Primeira fatia vertical da etapa 1B: derivar texto canônico dos artefatos de
texto já preservados e registrar candidatos determinísticos de
nomeação/exoneração em fila interna de revisão. Nada é publicado; o portal
público não muda; nenhum LLM participa.

## Desenho

- `workers/document-processing` (`barreiras_docproc`): módulo novo;
- texto canônico: UTF-8 estrito, quebras de linha normalizadas para LF,
  SHA-256 do texto normalizado, gravado em `raw.document_pages`
  (`extraction_method='embedded_text'`, página única,
  `parser_version=gazette-canonical-text/1.0.0`);
- candidatos: regras regex fixas e versionadas
  (`gazette-act-candidates/1.0.0`) para nomeação e exoneração, com offsets
  exatos no texto canônico e trecho de ±400 caracteres — reproduzíveis por
  qualquer pessoa com o mesmo texto;
- fila: um `extraction_job` por artefato e versão de regras (idempotente por
  chave derivada de conteúdo) e um `extraction_result` por candidato com
  `validation_status='needs_review'` e `confidence` nula — determinismo não
  finge probabilidade;
- cadeia de custódia: o texto restaurado do Storage é conferido contra o
  SHA-256 do artefato antes de qualquer derivação; o payload de cada candidato
  registra o hash do texto canônico e o hash do artefato de origem;
- execução: novo passo do workflow diário, após a coleta, com limite de 20
  artefatos por execução;
- permissões: `collector_worker` recebeu somente SELECT/INSERT nas três
  tabelas (migration aditiva aplicada ao projeto); UPDATE/DELETE continuam
  negados.

## Fatia 2 — campos determinísticos por candidato (31/07/2026)

Cada candidato passou a carregar `fields` no payload
(`schema_version 1.1.0`, `gazette-act-fields/1.0.0`): nome da pessoa, cargo,
símbolo e secretaria, extraídos por regras regex fixas na janela de 400
caracteres após o verbo do ato. Cada campo tem estado explícito —
`matched` com a regra que o encontrou ou `not_found` — e valor nulo quando
não encontrado: a incerteza é declarada por campo, nunca preenchida por
palpite. O nome exige sequência de palavras maiúsculas após o verbo
(tolerando ", a pedido," e quebras de linha); atos coletivos ("conforme
anexo") resultam em `not_found` e seguem para revisão humana do trecho.
Nomes em documentos totalmente em caixa alta podem capturar além do
esperado; o revisor humano vê o trecho completo ao lado dos campos, e a
régua (`gazette-act-fields`) é versionada para evoluir sem apagar
resultados anteriores.

## Fora de escopo (próximas fatias)

- extração de pessoa, cargo, órgão, data e vigência com incerteza por campo;
- amostra anotada e métricas de precisão/revocação com especialista;
- consumo da fila pelo portal admin (etapa 1C);
- PDFs sem texto (OCR) e PDFs hostis.

## Verificação

- 75 testes Python (12 novos): canonização (CRLF, determinismo, UTF-8
  inválido, vazio), regras (offsets reproduzíveis, caixa, janela nos limites
  do texto, negativos como "tornar sem efeito", ordem determinística) e
  serviço (payload com hashes, replay sem job duplicado, adulteração
  detectada);
- teste de migrations cobre as novas permissões e a ausência de
  UPDATE/DELETE;
- `ruff` limpo.

## Validação remota pendente

Após o merge, uma execução do workflow (manual ou a diária) deve processar os
dois textos preservados de 10/06/2026, criando dois jobs `succeeded`; o número
de candidatos esperado para essas edições é zero ou baixo, pois são atos de
"tornar sem efeito" e extratos de contrato — fila vazia é resultado legítimo e
explícito.
