# Data contracts

JSON Schema 2020-12 é a fonte canônica entre TypeScript, Python e PostgreSQL.
Mensagens internas carregam nome e versão. Mudança incompatível cria novo
arquivo/versão; não altera semanticamente uma versão existente.

Schemas iniciais:

- `collection-page`: página HTTP preservável e seu estado;
- `querido-diario-gazette-page`: resposta observada da API v0.19.0;
- `municipal-transparency-api-response`: raiz comum das APIs locais;
- `transferegov-parcerias-api-response`: envelope paginado observado na API
  pública de Gestão de Parcerias;
- `official-act-candidate`: extração candidata de nomeação/exoneração;
- `evidence-item`: trecho e origem que sustentam uma afirmação.

Contratos de fonte aceitam campos aditivos e continuam exigindo os campos
mínimos conhecidos. Descartar campo novo silenciosamente é proibido. Contratos
específicos por recurso serão criados junto ao respectivo conector e fixtures
sanitizadas.

O script `scripts/validate-schemas.mjs` faz validação estrutural sem dependências.
O bootstrap posterior deve adicionar validação completa com uma biblioteca
2020-12 fixada e lockfile.
