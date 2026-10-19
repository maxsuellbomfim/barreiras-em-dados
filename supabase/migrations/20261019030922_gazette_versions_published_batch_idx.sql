begin;

-- Índice do Diário (/diario): para escolher a página, a função conferia no
-- heap se cada uma das 1,4 mil edições tem documento publicado (1,5 s com
-- cache frio; timeouts às :18, logo após a sonda do pg_cron, em 18–19/10/2026).
-- Índice parcial dos lotes publicados: conferência só-índice (1.264 → 46
-- páginas lidas do disco, 62 ms). Sem mudança de resultado.
create index if not exists gazette_document_versions_published_batch_idx
  on editorial.gazette_document_versions (edition_year, edition, batch_idempotency_key)
  where publication_status in ('validated', 'edition_fallback')
    and published_at is not null;

commit;
