-- Garante que as RPCs publicas de emendas criadas na migration anterior
-- fiquem disponiveis no PostgREST imediatamente apos a aplicacao do lote.
-- NOTIFY e transacional: o catalogo so e recarregado depois do commit.
notify pgrst, 'reload schema';
