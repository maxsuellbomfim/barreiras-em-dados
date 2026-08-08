# Diário Oficial integral e segmentado — plano de implementação

> **Sub-skill obrigatória:** execute este plano com `superpowers:test-driven-development` e valide cada entrega com `superpowers:verification-before-completion`.

**Objetivo:** substituir os resumos incompletos do Diário Oficial por uma projeção pública fiel: texto oficial integral, separado em documentos somente quando os limites forem estruturalmente seguros, com fallback para a edição inteira quando houver dúvida.

**Arquitetura:** o PDF bruto e as páginas atuais continuam imutáveis. Uma nova camada deriva blocos ordenados, propõe limites de documentos, valida cobertura sem perdas e persiste uma versão append-only. A API pública expõe somente versões validadas. A página `/diario` deixa de consumir `edition_digest` e passa a mostrar documentos integrais ou um único bloco de edição integral.

**Stack:** Python 3.12, pypdf, OCR existente, PostgreSQL/Supabase, Next.js 16/TypeScript, Node test runner, pytest/unittest, GitHub Actions.

---

## Regras de segurança da entrega

- Nenhum resumo, paráfrase ou texto gerado por IA será publicado no Diário.
- Nenhum caractere de conteúdo poderá desaparecer entre o texto canônico da edição e a concatenação dos documentos publicados, exceto cabeçalho/rodapé repetitivo explicitamente classificado e auditado.
- A ordem original de páginas e blocos será preservada.
- IA poderá sugerir fronteiras, mas não poderá alterar texto nem liberar uma segmentação reprovada pelo validador.
- Havendo lacuna, sobreposição, quebra no meio de linha/palavra ou cobertura inconclusiva, será publicado um único documento `edition_fallback` com a edição inteira.
- A projeção antiga `edition_digest` será retirada da interface, mas os registros históricos permanecerão preservados.

## Tarefa 1 — Contratos de domínio e fixture de regressão

**Arquivos:**

- Criar: `workers/document-processing/src/barreiras_docproc/gazette_documents.py`
- Criar: `fixtures/sources/querido_diario/edition-4706-pages.json`
- Criar: `tests/document_processing/test_gazette_documents.py`
- Modificar: `fixtures/README.md`

### 1.1 Escrever primeiro os testes que falham

Definir casos para:

- blocos permanecem ordenados por `(page_number, block_order)`;
- o hash de cada bloco é SHA-256 do texto literal em UTF-8;
- um `GazetteDocumentDraft` contém `first_block`, `last_block`, `page_start`, `page_end`, `literal_title` e `full_text`;
- a concatenação canônica preserva a edição 4706 sem cortar `acompanhamento`, nomes, números de contrato ou parágrafos;
- títulos são transcritos de linhas existentes, nunca inventados.

Interface inicial:

```python
@dataclass(frozen=True)
class DocumentBlock:
    page_number: int
    block_order: int
    text: str
    sha256: str
    bbox: tuple[float, float, float, float] | None = None

@dataclass(frozen=True)
class GazetteDocumentDraft:
    first_block: int
    last_block: int
    page_start: int
    page_end: int
    literal_title: str
    full_text: str
    status: Literal["validated", "edition_fallback"]
```

### 1.2 Criar fixture representativa

Salvar em JSON uma amostra literal e pequena de blocos da edição 4706, incluindo:

- Portarias 261 e 262 completas;
- um edital de notificação;
- ao menos uma continuação de página;
- cabeçalho/rodapé repetido;
- hashes dos textos da fixture.

A fixture deve ser derivada do artefato oficial preservado e conter somente o necessário para regressão. Não deve conter resumo manual.

### 1.3 Implementar os tipos e helpers mínimos

Implementar `block_sha256`, `ordered_blocks` e `join_literal_blocks` sem segmentação ainda.

### 1.4 Verificar

```powershell
python -B -m pytest tests/document_processing/test_gazette_documents.py -q
python -B -m ruff check workers/document-processing/src/barreiras_docproc/gazette_documents.py tests/document_processing/test_gazette_documents.py
```

### 1.5 Commit

```text
feat(diario): criar contrato de documentos integrais
```

## Tarefa 2 — Extração de layout por página sem perda de texto

**Arquivos:**

- Criar: `workers/document-processing/src/barreiras_docproc/pdf_layout.py`
- Modificar: `workers/document-processing/src/barreiras_docproc/pdf_text.py`
- Criar: `tests/document_processing/test_pdf_layout.py`
- Modificar: `pyproject.toml` somente se a API de layout do pypdf existente não bastar

### 2.1 Escrever testes que falham

Cobrir:

- extração de linhas/blocos com página, ordem e coordenadas quando disponíveis;
- fallback ordenado quando o PDF não expõe coordenadas confiáveis;
- páginas escaneadas permanecem explicitamente pendentes de OCR;
- caracteres e números do texto embutido não são truncados;
- o texto canônico antigo e o novo apresentam a mesma cobertura textual normalizada.

### 2.2 Implementar a extração

Interface:

```python
@dataclass(frozen=True)
class PdfLayoutPage:
    page_number: int
    blocks: tuple[DocumentBlock, ...]
    extraction_method: Literal["embedded_layout", "embedded_text", "ocr"]

def derive_pdf_layout(raw_body: bytes) -> tuple[PdfLayoutPage, ...]: ...
```

Usar o mecanismo de visitantes do `pypdf` para capturar posição quando possível. Se a geometria estiver incompleta, manter a ordem de extração e marcar o método como `embedded_text`; nunca simular coordenadas.

### 2.3 Integrar sem quebrar o pipeline atual

`derive_pdf_text` continua disponível para finanças e atos. O novo pipeline chama `derive_pdf_layout`; ambos compartilham somente sanitização segura de caracteres de controle, sem resumir nem recortar conteúdo.

### 2.4 Verificar e commitar

```powershell
python -B -m pytest tests/document_processing/test_pdf_layout.py tests/document_processing/test_pdf_processing.py -q
python -B -m ruff check workers/document-processing/src/barreiras_docproc/pdf_layout.py workers/document-processing/src/barreiras_docproc/pdf_text.py
```

Commit: `feat(diario): extrair blocos ordenados dos PDFs`.

## Tarefa 3 — Segmentador estrutural conservador

**Arquivos:**

- Criar: `workers/document-processing/src/barreiras_docproc/gazette_segmentation.py`
- Criar: `tests/document_processing/test_gazette_segmentation.py`
- Modificar: `fixtures/sources/querido_diario/edition-4706-pages.json`

### 3.1 Escrever testes que falham

Casos obrigatórios:

- novo documento começa em título destacado/cabeçalho estrutural verificável;
- Portaria 261 não termina em `acomp` e inclui todo o ato até a próxima fronteira segura;
- Portaria 262 é documento separado;
- duas ou mais pessoas no mesmo ato continuam no mesmo documento;
- continuação de página não cria documento novo;
- texto em caixa alta sozinho não é suficiente para uma divisão;
- dúvida de fronteira retorna uma proposta inconclusiva, não um corte otimista;
- tipos organizacionais são opcionais e não controlam a integridade do texto.

### 3.2 Implementar propostas de fronteira

```python
@dataclass(frozen=True)
class BoundaryProposal:
    start_block: int
    evidence: tuple[str, ...]
    confidence: Decimal
    source: Literal["layout", "deterministic", "ai_assist"]

def propose_boundaries(
    blocks: Sequence[DocumentBlock],
) -> tuple[BoundaryProposal, ...]: ...
```

Sinais permitidos incluem quebra visual forte, espaçamento, tamanho/fonte quando disponível, início de página e padrões de cabeçalho completos. Regex de palavras como “PORTARIA” ou “AVISO” pode reforçar uma fronteira, mas nunca autoriza sozinha cortar o texto.

### 3.3 Materializar rascunhos

Implementar `build_document_drafts(blocks, proposals)` sem alterar o texto dos blocos. O título literal deve ser selecionado dentro do próprio primeiro bloco e ser verificável por substring exata.

### 3.4 Verificar e commitar

```powershell
python -B -m pytest tests/document_processing/test_gazette_segmentation.py -q
python -B -m ruff check workers/document-processing/src/barreiras_docproc/gazette_segmentation.py
```

Commit: `feat(diario): segmentar edicoes por estrutura documental`.

## Tarefa 4 — Validador de integridade e fallback integral

**Arquivos:**

- Criar: `workers/document-processing/src/barreiras_docproc/gazette_integrity.py`
- Criar: `tests/document_processing/test_gazette_integrity.py`
- Modificar: `workers/document-processing/src/barreiras_docproc/gazette_segmentation.py`

### 4.1 Escrever testes que falham

Reprovar segmentações com:

- bloco ausente;
- bloco repetido ou sobreposto;
- ordem trocada;
- texto alterado;
- título que não existe literalmente no documento;
- começo/fim no meio de linha ou palavra;
- página OCR pendente;
- remoção de cabeçalho/rodapé não registrada.

Confirmar que qualquer reprovação retorna exatamente um `edition_fallback`, com todos os blocos na ordem original e texto integral.

### 4.2 Implementar validação determinística

```python
@dataclass(frozen=True)
class IntegrityReport:
    valid: bool
    errors: tuple[str, ...]
    source_sha256: str
    documents_sha256: str
    blocks_expected: int
    blocks_observed: int

def validate_or_fallback(
    blocks: Sequence[DocumentBlock],
    drafts: Sequence[GazetteDocumentDraft],
) -> tuple[tuple[GazetteDocumentDraft, ...], IntegrityReport]: ...
```

Comparar uma representação canônica composta por identificador do bloco + hash + ordem. Não comparar apenas texto unido, pois isso não detecta sobreposição com o mesmo conteúdo.

### 4.3 Verificar e commitar

```powershell
python -B -m pytest tests/document_processing/test_gazette_integrity.py tests/document_processing/test_gazette_segmentation.py -q
```

Commit: `feat(diario): bloquear segmentacao com perda de conteudo`.

## Tarefa 5 — Persistência append-only e API pública

**Arquivos:**

- Criar: `supabase/migrations/20260808233000_integral_gazette_documents.sql`
- Criar: `packages/database/scripts/test-integral-gazette-documents.mjs`
- Modificar: `package.json`

### 5.1 Escrever o teste de migration que falha

Executar a migration em PGlite e verificar:

- schemas, tabelas, índices, constraints e RLS;
- imutabilidade de `raw.document_blocks`;
- append-only/supersessão de `editorial.gazette_document_versions`;
- função pública não lê JSON arbitrário de `raw.extraction_results`;
- `anon` só executa a RPC pública;
- a API não retorna texto de versões não publicadas;
- a API não expõe confiança interna, prompts, segredos ou conteúdo sensível.

### 5.2 Criar as relações

```sql
create table raw.document_blocks (
  id uuid primary key default gen_random_uuid(),
  document_page_id uuid not null references raw.document_pages(id),
  block_order integer not null check (block_order >= 0),
  text_content text not null check (length(text_content) > 0),
  text_sha256 text not null check (text_sha256 ~ '^[0-9a-f]{64}$'),
  bbox jsonb,
  extraction_method text not null,
  extractor_version text not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (document_page_id, block_order, extractor_version)
);
```

Criar `editorial.gazette_document_versions` com artefato, edição, ano, ordem, primeiro/último bloco, página inicial/final, título literal, tipo opcional, texto integral, hash, status `validated|edition_fallback|superseded|withdrawn`, versões do segmentador/validador e timestamps.

### 5.3 Criar projeção pública tipada

Função `api.get_integral_gazette_editions(page_size integer default 20)` retorna uma linha por edição com metadados oficiais e `documents jsonb`, já ordenados. Cada documento público contém somente:

```json
{
  "document_id": "uuid",
  "document_order": 1,
  "literal_title": "PORTARIA Nº 261, DE 29 DE JULHO DE 2026",
  "document_type": "portaria",
  "page_start": 3,
  "page_end": 4,
  "full_text": "...texto integral...",
  "text_sha256": "...",
  "publication_status": "validated"
}
```

### 5.4 Registrar retirada da projeção antiga sem apagar histórico

A migration deve impedir que novas versões `edition_digest` sejam projetadas publicamente e registrar comentário de depreciação na RPC antiga. Não apagar `raw.extraction_results` nem revisões históricas.

### 5.5 Verificar e commitar

```powershell
node packages/database/scripts/test-integral-gazette-documents.mjs
pnpm.cmd run check:migration
```

Commit: `feat(database): persistir documentos integrais do Diario`.

## Tarefa 6 — Repositório e comando idempotente de processamento

**Arquivos:**

- Criar: `workers/document-processing/src/barreiras_docproc/gazette_repository.py`
- Criar: `workers/document-processing/src/barreiras_docproc/commands/segment_gazette_editions.py`
- Criar: `tests/document_processing/test_segment_gazette_command.py`
- Criar: `tests/document_processing/test_gazette_repository_contract.py`
- Modificar: `workers/document-processing/src/barreiras_docproc/processing.py`

### 6.1 Escrever testes que falham

Cobrir:

- seleciona somente artefatos completos, com todas as páginas em texto ou OCR;
- processa a edição mais recente primeiro;
- idempotência inclui hash do artefato, versão do extrator, segmentador e validador;
- reexecução não duplica documentos;
- versão nova supersede a anterior sem update/delete do bruto;
- falha de uma edição não impede as demais e gera registro sanitizado;
- segmentação inválida persiste somente o fallback integral;
- nenhuma chamada a provedor de IA é necessária para publicar o texto integral.

### 6.2 Implementar repositório isolado

Não ampliar `postgres.py`, que já concentra responsabilidades. O novo `GazetteDocumentRepository` deve expor:

```python
def pending_artifacts(limit: int) -> Sequence[GazetteArtifact]: ...
def page_inputs(artifact_id: str) -> Sequence[PageInput]: ...
def persist_version(batch: GazetteDocumentBatch) -> PersistResult: ...
def record_failure(artifact_id: str, code: str, detail: str) -> None: ...
```

### 6.3 Implementar comando

`python -B -m barreiras_docproc.commands.segment_gazette_editions --limit 6`:

1. recupera páginas completas;
2. deriva blocos;
3. propõe fronteiras;
4. valida ou produz fallback;
5. persiste versão;
6. registra métricas estruturadas: documentos, blocos, páginas, status, hashes e versão.

### 6.4 Verificar e commitar

```powershell
python -B -m pytest tests/document_processing/test_segment_gazette_command.py tests/document_processing/test_gazette_repository_contract.py -q
python -B -m ruff check workers/document-processing/src/barreiras_docproc/gazette_repository.py workers/document-processing/src/barreiras_docproc/commands/segment_gazette_editions.py
```

Commit: `feat(diario): processar e persistir edicoes integrais`.

## Tarefa 7 — Contrato TypeScript e interface pública

**Arquivos:**

- Criar: `apps/web/lib/integral-gazette-documents.ts`
- Modificar: `apps/web/app/diario/page.tsx`
- Modificar: `apps/web/app/globals.css`
- Criar: `tests/web/integral-gazette-documents-contract.test.mjs`
- Modificar: `tests/web/local-assistance-contract.test.mjs`

### 7.1 Escrever o teste de contrato que falha

Verificar que:

- a página chama `get_integral_gazette_editions`;
- o parser rejeita documentos sem hash, texto, ordem ou páginas válidas;
- o texto integral é renderizado em `<pre>`/bloco preservando quebras;
- a copy não usa “resumo”, “traduzido”, “explicação em palavras simples” ou “IA”;
- fallback é identificado como “Edição integral — separação segura indisponível”;
- o PDF oficial e o hash continuam visíveis;
- a edição mais recente vem primeiro;
- documentos ficam recolhidos inicialmente, com título, tipo e páginas aparentes;
- pesquisa client-side filtra dentro de títulos e texto sem modificar o conteúdo.

### 7.2 Criar parser tipado

Tipos:

```typescript
type GazetteDocument = Readonly<{
  documentId: string;
  documentOrder: number;
  literalTitle: string;
  documentType: string | null;
  pageStart: number;
  pageEnd: number;
  fullText: string;
  textSha256: string;
  publicationStatus: "validated" | "edition_fallback";
}>;
```

Em qualquer payload inválido, retornar estado `unavailable`; nunca renderizar parcialmente uma edição.

### 7.3 Reescrever `/diario`

- título: “Diário Oficial organizado”;
- subtítulo: explicar que o texto é integral e apenas separado por documento;
- card da edição: número, data, fonte, quantidade de documentos, busca;
- `<details>` por documento, fechado por padrão;
- conteúdo integral em tipografia legível, com rolagem horizontal somente quando indispensável;
- selo de fallback quando não houver divisão segura;
- remover completamente `DigestCard`, `ItemRow` e mensagens de resumo/IA.

### 7.4 Verificar e commitar

```powershell
node --test tests/web/integral-gazette-documents-contract.test.mjs tests/web/local-assistance-contract.test.mjs
pnpm.cmd --filter @barreiras-em-dados/web run build
```

Commit: `feat(web): publicar Diario integral organizado`.

## Tarefa 8 — Workflow, backfill e desligamento do digest

**Arquivos:**

- Modificar: `.github/workflows/collect-querido-diario.yml`
- Modificar: `.github/workflows/backfill-gazette-acts.yml`
- Criar: `tests/workflows/integral-gazette-workflow.test.mjs`
- Modificar: `tests/workflows/scheduled-commands.test.mjs`
- Modificar: `docs/operations/QUERIDO_DIARIO_RUNBOOK.md` ou o runbook equivalente encontrado no repositório

### 8.1 Escrever testes que falham

- nenhum workflow chama `digest_gazette_editions`;
- coleta diária chama `segment_gazette_editions` após OCR;
- backfill aceita limite e retoma por checkpoint;
- falha de segmentação é registrada, mas não apaga artefatos;
- publicação integral não depende de chaves de IA;
- inputs de Actions passam por variáveis de ambiente, nunca interpolação direta no shell.

### 8.2 Atualizar workflows

Substituir:

```yaml
- name: Resumir edições com âncoras verificadas
  run: python -B -m barreiras_docproc.commands.digest_gazette_editions --limit 6
```

por:

```yaml
- name: Organizar edições em documentos integrais
  env:
    PYTHONPATH: workers/collectors/src:workers/document-processing/src
  run: >-
    python -B -m barreiras_docproc.commands.segment_gazette_editions
    --limit 6
```

O passo não terá segredos de IA. Manter OCR e extração de atos em caminhos independentes: a página do Diário não pode depender da fila de nomeações/exonerações.

### 8.3 Verificar e commitar

```powershell
node --test tests/workflows/integral-gazette-workflow.test.mjs tests/workflows/scheduled-commands.test.mjs
python -B -c "import yaml, pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('.github/workflows').glob('*.yml')]"
```

Commit: `ci(diario): automatizar publicacao integral e backfill`.

## Tarefa 9 — Verificação ponta a ponta e documentação

**Arquivos:**

- Modificar: `docs/DATA_GOVERNANCE.md`
- Modificar: `docs/ARCHITECTURE.md`
- Modificar: `docs/EDITORIAL_POLICY.md`
- Modificar: `docs/operations/QUERIDO_DIARIO_RUNBOOK.md` ou equivalente
- Criar: `docs/reviews/2026-08-08-integral-gazette-security-data-quality.md`

### 9.1 Rodar regressão completa

```powershell
python -B -m pytest tests/document_processing tests/collectors -q
python -B -m ruff check workers/document-processing workers/collectors tests/document_processing tests/collectors
pnpm.cmd test
pnpm.cmd run check:contracts
pnpm.cmd run check:migration
pnpm.cmd --filter @barreiras-em-dados/web run build
git diff --check
```

### 9.2 Fazer auditoria específica da edição 4706

Gerar relatório determinístico contendo:

- hash do artefato;
- páginas/blocos esperados e observados;
- documentos produzidos;
- cobertura 100% ou fallback;
- primeira e última linha de cada documento;
- confirmação de que `acompanhamento` e todos os finais de parágrafo permanecem completos.

Não declarar sucesso com inspeção visual parcial. Comparar hashes e cobertura.

### 9.3 Revisar segurança e qualidade de dados

- RLS e grants mínimos;
- nenhum texto bruto acessível por tabela direta;
- nenhum segredo/CPF/log interno na API;
- nenhum documento sem artefato/hash/origem;
- fallback obrigatório para incerteza;
- correções append-only e auditáveis.

### 9.4 Atualizar documentação e commitar

Commit: `docs(diario): documentar publicacao integral verificavel`.

## Critérios finais de aceitação

- `/diario` não contém resumo nem paráfrase.
- Cada documento exibido contém texto oficial integral e hash.
- Toda edição validada tem cobertura exata de blocos, sem lacunas ou sobreposição.
- Toda edição não validada aparece inteira em um único fallback.
- Edição 4706 passa na regressão sem texto truncado.
- Coleta diária e backfill publicam sem depender de IA.
- Digests antigos não aparecem no site, mas continuam preservados no histórico.
- Testes Python, Node, migrations, contratos, workflow, build e `git diff --check` passam.

## Ordem de entrega em PRs

1. **PR A — núcleo seguro:** tarefas 1 a 4.
2. **PR B — persistência e comando:** tarefas 5 e 6.
3. **PR C — interface e automação:** tarefas 7 e 8.
4. **PR D — backfill validado e documentação:** tarefa 9 e reprocessamento controlado.

Essa separação mantém cada PR revisável e evita publicar a interface nova antes de o banco e o validador estarem estáveis.
