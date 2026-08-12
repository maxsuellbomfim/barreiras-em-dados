-- A role collector_worker nao recebe USAGE no schema extensions. A validacao
-- deferida precisa chamar pgcrypto sem ampliar os privilegios da role tecnica.
-- SECURITY DEFINER e seguro aqui porque a funcao nao recebe argumentos, tem
-- search_path vazio, e sua execucao direta permanece revogada.

alter function source.verify_official_document_search_evidence()
  security definer;

revoke all on function source.verify_official_document_search_evidence()
  from public, anon, authenticated, collector_worker;
