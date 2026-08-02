# Financial Automatic Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair o primeiro relatório municipal de receitas a partir de PDFs preservados e publicar automaticamente somente linhas determinísticas validadas, com backfill controlado.

**Architecture:** O parser continua puro e sem acesso a rede. Um publicador separado lê artefatos PDF filhos do Storage, transforma o relatório em linhas tipadas, registra proveniência e grava versões publicáveis no PostgreSQL. A função pública expõe apenas linhas com `validation_status = 'validated'` e `published_at` preenchido.

**Tech Stack:** Python 3.12, `Decimal`, `psycopg`, Supabase Storage, PostgreSQL migrations, unittest/pytest-compatible fixtures, GitHub Actions.

## Global Constraints

- Totais e comparações serão produzidos por código determinístico; a IA não fará cálculos.
- Todo valor público terá fonte, hash, período, parser e metodologia.
- Falhas de evidência nunca serão convertidas em zero.
- Correções criarão versões novas e preservarão as anteriores.
- O publicador será idempotente e não publicará conflitos de fonte.
- Anomalias não serão tratadas como prova de irregularidade.

---

### Task 1: Tornar o relatório de receita um contrato publicável

**Files:**
- Modify: `workers/normalization/src/barreiras_normalization/financial_revenue_pdf.py`
- Create: `workers/normalization/src/barreiras_normalization/revenue_publication.py`
- Modify: `tests/normalization/test_revenue.py`
- Create: `tests/normalization/test_revenue_publication.py`

**Interfaces:**
- Consumes: `RevenuePdfReport` e `RevenuePdfRow` existentes.
- Produces: `RevenuePublicationRow`, `RevenuePublicationBatch` e `validate_publication_batch(report)`.

- [x] **Step 1: Write failing tests**

```python
def test_publication_uses_period_amount_and_keeps_accumulated_amount():
    batch = build_publication_batch(sample_report())
    assert batch.rows[0].collected_amount == Decimal("1200.00")
    assert batch.rows[0].accumulated_amount == Decimal("2400.00")
    assert batch.methodology_version == "public-revenue-pdf/1.0.0"

def test_publication_rejects_negative_or_non_finite_money():
    report = replace(sample_report(), rows=(replace(sample_report().rows[0], period_amount=Decimal("-1.00")),))
    with pytest.raises(RevenuePublicationError):
        build_publication_batch(report)
```

- [x] **Step 2: Run the focused tests and confirm failure**

Run: `python -m unittest tests.normalization.test_revenue tests.normalization.test_revenue_publication -v`

Expected: FAIL because the publication contract does not exist.

- [x] **Step 3: Implement the pure contract**

Add immutable dataclasses with `Decimal` fields. Map `period_amount` to the public `collected_amount`, preserve `accumulated_amount`, `forecast_amount`, `difference_more` and `difference_less`, and require the declared total line to be present and parseable. For revenue codes beginning with `9`, preserve accounting direction as `deduction` while storing magnitudes as non-negative values; all other rows use `credit`. Reject non-finite values, reject duplicate codes, and compute a canonical batch digest from the ordered rows.

- [x] **Step 4: Run tests and Ruff**

Run: `python -m unittest tests.normalization.test_revenue tests.normalization.test_revenue_publication -v` and `python -m ruff check workers/normalization tests/normalization`.

Expected: PASS with no floating-point conversion.

- [x] **Step 5: Commit**

```bash
git add workers/normalization tests/normalization
git commit -m "feat: criar contrato publicável de receitas"
```

### Task 2: Versionar proveniência e status no banco

**Files:**
- Create: `supabase/migrations/20260805010000_finance_revenue_automation.sql`
- Modify: `packages/database/scripts/test-foundation-migration.mjs`

**Interfaces:**
- Consumes: `finance.revenues`, `raw.raw_artifacts`, `raw.raw_records`, `org.public_bodies`.
- Produces: columns `source_document_artifact_id`, `accumulated_amount`, `difference_more`, `difference_less`, `methodology_version`, `validation_status`, `published_at` and a public RPC version `public-revenues/1.1.0`.

- [x] **Step 1: Add a structural migration assertion**

Assert that `finance.revenues` has the new provenance and validation columns, that `validation_status` accepts `extracted`, `validated`, `needs_source`, `needs_review`, `superseded`, and that the public RPC filters to `validated` rows with a publication timestamp.

- [x] **Step 2: Run the migration test and confirm failure**

Run: `pnpm run check:migration`.

Expected: FAIL until the migration and assertions are present.

- [x] **Step 3: Implement the migration**

Add nullable child-artifact and report-column fields, `collection_direction` with `credit`/`deduction`, default `methodology_version` to `public-revenue-pdf/1.0.0`, enforce non-negative stored magnitudes, add an index for `(public_body_id, fiscal_year, validation_status)`, replace `api.get_public_revenues(integer, smallint)` with methodology `public-revenues/1.1.0` and a signed amount projection, and grant only `anon`/`authenticated` execution. Keep previous rows queryable through their version and status.

- [x] **Step 4: Run the migration check**

Run: `pnpm run check:migration && pnpm run check:contracts`.

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add supabase/migrations/20260805010000_finance_revenue_automation.sql packages/database/scripts/test-foundation-migration.mjs
git commit -m "feat: versionar publicação de receitas"
```

### Task 3: Criar publicador idempotente de artefatos financeiros

**Files:**
- Create: `workers/normalization/src/barreiras_normalization/revenue_publisher.py`
- Create: `workers/normalization/src/barreiras_normalization/commands/publish_revenue_reports.py`
- Create: `tests/normalization/test_revenue_publisher.py`

**Interfaces:**
- Consumes: `RevenuePublicationBatch`, `ObjectReader`, `RevenuePublicationRepository` e `PostgresCollectionRepository` connection factory.
- Produces: `publish_pending_reports(limit: int) -> PublishSummary` e CLI `python -m barreiras_normalization.commands.publish_revenue_reports --limit N`.

- [x] **Step 1: Write failing publisher tests**

```python
def test_publisher_rejects_tampered_pdf_before_insert():
    repository = FakeRevenueRepository()
    publisher = RevenueReportPublisher(FakeReader(b"pdf"), repository)
    with pytest.raises(ArtifactMismatchError):
        publisher.publish(artifact_with_wrong_hash())

def test_publisher_replays_without_duplicate_rows():
    repository = FakeRevenueRepository()
    publisher = RevenueReportPublisher(FakeReader(valid_pdf_bytes), repository)
    first = publisher.publish(valid_artifact())
    second = publisher.publish(valid_artifact())
    assert first.published_rows == 1
    assert second.published_rows == 0
    assert len(repository.inserted_batches) == 1
```

- [x] **Step 2: Run the focused tests and confirm failure**

Run: `python -m unittest tests.normalization.test_revenue_publisher -v`.

Expected: FAIL because the publisher does not exist.

- [x] **Step 3: Implement hash verification and deterministic persistence**

Read the object by key, verify SHA-256 and byte size, extract canonical text through the existing PDF text service, parse the report, build a publication batch, and call a repository method that inserts the municipal executive body from the parent raw record when absent. Insert each line with `source_document_artifact_id`, `origin_raw_record_id`, `validation_status = 'validated'`, `published_at`, methodology and a stable external id composed of PDF hash plus revenue code. Any parser or reconciliation failure creates no public rows and returns `needs_review`.

- [x] **Step 4: Implement the CLI with bounded backfill**

Accept `--limit` from 1 to 100, `--fiscal-year-from` from 2021 to the current year, and `--fiscal-year-to`. Select only municipal-transparency document artifacts whose metadata schema is `municipal-transparency-document`, whose parent record is a financial resource, and which have no validated publication for the same artifact hash. Log `published_rows`, `needs_source`, `needs_review`, and `skipped_existing` as structured metrics.

- [x] **Step 5: Run tests and Ruff**

Run: `python -m unittest tests.normalization.test_revenue_publisher -v` and `python -m ruff check workers/normalization tests/normalization`.

Expected: PASS; replay is idempotent and persistence corruption aborts the run.

- [x] **Step 6: Commit**

```bash
git add workers/normalization tests/normalization
git commit -m "feat: publicar receitas validadas de PDFs"
```

### Task 4: Integrar a publicação automática ao workflow

**Files:**
- Create: `.github/workflows/publish-financial-revenues.yml`
- Modify: `docs/reviews/FINANCE_DOCUMENT_CATALOG.md`
- Modify: `docs/superpowers/specs/2026-08-02-financial-auto-publication-design.md`

**Interfaces:**
- Consumes: `publish_revenue_reports` CLI and existing Supabase workload secrets.
- Produces: scheduled/manual backfill workflow with bounded concurrency.

- [x] **Step 1: Add workflow contract test**

Assert that the workflow uses Python 3.12, `PERSISTENCE_MODE=postgres-supabase`, the existing database/storage secrets, `--limit 50`, and year bounds beginning at 2021.

- [x] **Step 2: Implement daily and manual workflow**

Run the publisher after document collection, with `workflow_dispatch` inputs for `fiscal_year_from`, `fiscal_year_to` and `limit`, timeout 20 minutes, concurrency `publish-financial-revenues-production`, and no secrets printed in logs.

- [x] **Step 3: Update runbook**

Document that collection must run before publication, that only `validated` rows appear in `/financas`, and that a missing year means no validated source was found rather than zero revenue.

- [x] **Step 4: Run workflow and contract checks**

Run: `pnpm run check:contracts`, `pnpm run check:migration`, the full normalization tests, web build/typecheck, and `git diff --check`.

- [x] **Step 5: Commit**

```bash
git add .github/workflows/publish-financial-revenues.yml docs/reviews/FINANCE_DOCUMENT_CATALOG.md docs/superpowers/specs/2026-08-02-financial-auto-publication-design.md
git commit -m "feat: automatizar publicação de receitas"
```

### Task 5: Expor metodologia e cobertura no portal

**Files:**
- Modify: `apps/web/lib/revenues.ts`
- Modify: `apps/web/app/financas/page.tsx`
- Create: `tests/web/revenues-contract.test.mjs`

**Interfaces:**
- Consumes: RPC `api.get_public_revenues` version `public-revenues/1.1.0`.
- Produces: cards that show accumulated amount, source document, validation status, methodology and coverage note.

- [x] **Step 1: Write the contract test**

Reject payloads whose methodology is not `public-revenues/1.1.0`, whose validation status is not `validated`, or whose document hash is invalid.

- [x] **Step 2: Update parser and page copy**

Add fields with strict runtime validation. Show “publicado automaticamente após validação determinística” and a link to the official source. Show “sem dado validado para este período” when the result is empty; never render zero as a substitute.

- [x] **Step 3: Run web checks**

Run: `pnpm --filter @barreiras-em-dados/web build` and `pnpm --filter @barreiras-em-dados/web typecheck`.

- [x] **Step 4: Commit**

```bash
git add apps/web tests/web
git commit -m "feat: exibir receitas e cobertura validadas"
```

### Task 6: Review, PR and staged activation

**Files:**
- No new source files; review all files changed by Tasks 1–5.

- [x] **Step 1: Run the complete verification set**

Run: collector suite, normalization suite, document-processing suite, migration/contracts checks, web build/typecheck, Ruff and `git diff --check`.

- [x] **Step 2: Inspect the diff for policy regressions**

Confirm no automatic accusation, no LLM arithmetic, no full CPF, no raw schema exposure, and no destructive update/delete path.

- [x] **Step 3: Open a PR**

Use title `feat: publicar receitas municipais validadas` and include the activation order: merge, apply migration, collect PDFs, run publisher with a small limit, inspect `/financas`, then expand backfill.

- [x] **Step 4: Commit any final documentation correction**

```bash
git add .
git commit -m "docs: registrar ativação da publicação financeira"
```
