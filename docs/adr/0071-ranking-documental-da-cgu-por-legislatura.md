# ADR 0071 — Ranking documental da CGU por legislatura

## Contexto

O ranking federal por legislatura ainda consumia o retrato agregado da CGU,
cujo recorte territorial auditado terminava em 2023. A série anual por
documento já cobre 2021 até o exercício corrente e preserva separadamente
empenhos, liquidações e pagamentos.

O ano em que um documento financeiro foi emitido pode ser posterior ao ano da
emenda. Usar o ano do documento para definir o mandato atribuiria a autoria à
legislatura errada.

## Decisão

- O ranking da CGU por legislatura usará somente
  `territory.cgu_federal_amendment_documents`.
- A legislatura será definida por `amendment_year`; `archive_year` e
  `document_date` continuarão indicando quando a execução foi publicada.
- Empenhos e pagamentos serão somados em colunas separadas. Liquidações não
  serão tratadas como pagamento.
- O ranking continuará ordenado pelo valor empenhado e, em caso de empate,
  pelo valor pago; a interface mostrará explicitamente os dois estágios.
- O ano de transição 2023 ficará fora do ranking enquanto a fonte não trouxer a
  data de autoria necessária para separar as duas legislaturas.
- A série documental nunca será somada ao retrato agregado da CGU nem ao
  Transferegov.
- Um perfil político só será associado por código oficial, período compatível
  e crosswalk aprovado. Nomes semelhantes não produzirão vínculo automático.

## Consequências

- A 57ª Legislatura passa a refletir documentos de emendas de 2024 em diante.
- Pagamentos posteriores permanecem ligados ao ano original da emenda sem
  serem retroativamente atribuídos a outro mandato.
- Autoria coletiva continua separada de parlamentares individuais.
- A ausência de linha documental é descrita como “não encontrada nesta fonte”
  e nunca como valor zero ou falta de trabalho do parlamentar.
- O ranking mede somente execução documental encontrada para Barreiras; não é
  uma avaliação completa de desempenho político.
