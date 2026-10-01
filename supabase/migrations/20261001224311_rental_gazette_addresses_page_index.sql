begin;

-- Índice da chave estrangeira para a página do Diário (aluguéis 1.4.0).
create index rental_gazette_addresses_document_page_idx
  on finance.rental_gazette_addresses (document_page_id);

commit;
