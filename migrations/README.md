# Migrations

As migrations executáveis vivem em `supabase/migrations/` e devem ser criadas
com `supabase migration new`, nunca com nome inventado. Esta pasta permanece
como ponto de navegação exigido pela estrutura do monorepo.

A fundação inicial está em:

- `supabase/migrations/20260730193814_initial_public_data_foundation.sql`;
- `supabase/seed.sql`.

Não altere uma migration já aplicada em ambiente compartilhado. Gere uma nova
migration corretiva.
