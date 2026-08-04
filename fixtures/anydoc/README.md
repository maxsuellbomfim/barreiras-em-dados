# Corpus local do benchmark AnyDoc

Este diretório recebe somente cópias de documentos públicos, sem CPF completo,
credenciais ou dados pessoais desnecessários. Não incluímos documentos reais no
repositório sem revisar tamanho, licença e necessidade de redistribuição.

Para o primeiro benchmark, montar 20 arquivos:

- 4 PDFs textuais do Diário Oficial;
- 4 PDFs com tabelas de licitação/contratos;
- 4 PDFs escaneados ou mistos;
- 3 XLSX/CSV financeiros;
- 3 DOCX/ODT de editais e termos de referência;
- 2 documentos de leis ou indicações.

Preservar em um manifesto externo a URL oficial, data de coleta e SHA-256.
Executar:

```text
PYTHONPATH=workers/document-processing/src \
python workers/document-processing/scripts/benchmark_anydoc.py \
  fixtures/anydoc --output artifacts/anydoc-benchmark.json
```

O relatório contém apenas metadados, hashes, tempos e status. O texto não é
impresso nem versionado.
