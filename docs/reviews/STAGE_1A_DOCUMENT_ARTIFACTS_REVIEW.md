# Revisão da etapa 1A — PDF/texto como artefatos filhos

Data: 31/07/2026.

## Escopo

Esta entrega baixa o PDF e o texto de cada edição anunciada pela API do
Querido Diário e os preserva como artefatos filhos da página JSON que os
anunciou. Nenhum conteúdo é interpretado, extraído ou publicado; o portal
público não muda.

## Desenho

- `GazetteDocumentClient` baixa um documento por vez, somente dos hosts
  oficiais já permitidos (`ALLOWED_ARTIFACT_HOSTS`), com validação HTTPS,
  redirects restritos, retries com jitter, rate limit compartilhado,
  circuit breaker e limite de tamanho por documento;
- cada documento vira uma linha em `raw.raw_artifacts` com
  `artifact_kind='document'`, `parent_artifact_id` apontando para a página
  JSON coletada e `metadata.source_record_key` ligando à edição específica;
- o objeto é gravado no bucket privado sob
  `querido-diario/gazettes/documents/sha256/<h2>/<sha256>.<pdf|txt>`, dentro
  do único prefixo autorizado à identidade técnica do Storage;
- a idempotência é por conteúdo:
  `sha256("gazette-document:<record_key>:<papel>:<sha256 do corpo>")`;
  replay não duplica e mudança de conteúdo na fonte cria nova versão sem
  apagar a anterior;
- limites explícitos por execução (`QUERIDO_DIARIO_MAX_DOCUMENT_BYTES`,
  `QUERIDO_DIARIO_MAX_DOCUMENTS_PER_RUN`); quando o orçamento é atingido, o
  restante é registrado em log estruturado — nunca truncado em silêncio — e o
  replay da mesma janela completa o que faltou;
- falha de download após retries interrompe a execução com erro explícito; o
  workflow registra a falha sanitizada e preserva a DLQ, como já fazia.

## Qualidade dos dados

- o status público (`api.get_querido_diario_collection_status`) filtra
  `artifact_kind='http_response'`, portanto os novos artefatos `document`
  não alteram o significado dos números exibidos no portal;
- a restauração pós-upload confere SHA-256 e tamanho antes do registro no
  banco; adulteração do objeto é detectada no replay.

## Verificação

- 58 testes Python (14 novos): cliente de documentos (sucesso, retry,
  falha permanente, esgotamento, host proibido), persistência (prefixo,
  vínculo pai-filho, idempotência, adulteração, hash divergente, papel
  desconhecido), repositório local (manifesto único, identidade estável) e
  comando de ponta a ponta (3 documentos da fixture, replay limpo,
  orçamento com log de pulados);
- `ruff check` sem apontamentos;
- contratos, catálogo de fontes e migration em banco descartável seguem
  passando.

## Incidente da primeira validação remota (31/07/2026)

A execução manual nº 4 do workflow falhou no primeiro documento: o CDN do
Querido Diário anuncia `Content-Type: binary/octet-stream`, tipo ausente da
lista de MIME permitidos do bucket, e o Storage recusou o upload. Nenhum
objeto ou linha parcial foi gravado — a falha foi explícita, como desenhado.
Correção: o coletor passou a classificar o content-type pelo papel anunciado
(`txt` → `text/plain`, `pdf` → `application/pdf`), preservando o header
observado em `response_headers`, e a validar o corpo baixado (PDF deve começar
com `%PDF-`; documento vazio é recusado), o que também detecta páginas de erro
servidas como HTTP 200. Reproduzido e verificado localmente contra a API real
antes do replay remoto.

## Limitações e próxima validação

- a validação remota ainda não ocorreu: requer um disparo manual do workflow
  com a janela `2026-06-10` a `2026-06-10` para baixar os documentos das duas
  edições já preservadas, ou a próxima janela diária com edições novas;
- não há OCR, extração ou leitura do conteúdo dos PDFs nesta fatia (Etapa 1B);
- a visão interna de lacunas, o exercício integrado de DLQ/circuit breaker e a
  revisão de backup continuam pendentes para encerrar a 1A.
