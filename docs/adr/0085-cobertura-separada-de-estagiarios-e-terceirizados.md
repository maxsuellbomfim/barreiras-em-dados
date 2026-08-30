# ADR 0085 — Cobertura separada de estagiários e terceirizados

## Contexto

O catálogo `servidores` da Prefeitura lista relações distintas de servidores,
estagiários e terceirizados. Os títulos oficiais exatos prevalecem sobre
`tipo=3` e `tipo=4`, pois a fonte já classificou uma relação de estagiários
como `tipo=1`. Esses relatórios não têm o mesmo conceito da folha regular e podem conter CPF, dados bancários e valores
individuais. Somá-los à folha distorceria o custo mensal e ampliaria a exposição
de dados pessoais.

Em 30/08/2026, uma auditoria privada e somente leitura conferiu SHA-256 e
tamanho dos PDFs preservados de estagiários das competências 2026-08, 2025-11
e 2024-12. Os dois modos de extração textual disponíveis não reconciliaram as
colunas com um total declarado. O documento de 2024 também combina páginas sem
texto embutido útil. Uma amostra de terceirizados de 2026-08 é integralmente
escaneada e não apresentou total global verificável na inspeção estrutural.

## Decisão

Criar `api.get_public_nonpayroll_workforce_coverage`, uma projeção pública
separada que retorna apenas:

- competência e categoria oficial;
- estado `not_listed`, `catalogued` ou `document_preserved`;
- contagens de documentos catalogados e preservados;
- URL HTTPS do catálogo oficial, hash de uma evidência preservada e data da
  conferência;
- nota metodológica que proíbe interpretar ausência como gasto zero.

A função parte exclusivamente da última partição completa do catálogo. O
frontend valida um esquema fechado e não aceita nome, CPF, conta bancária nem
campo monetário nesse contrato.

## Consequências

- estagiários e terceirizados permanecem fora do total da folha regular;
- o portal torna visível o que foi ou não localizado e preservado, sem inventar
  valores;
- totais agregados futuros exigirão parser versionado, reconciliação integral em
  múltiplos leiautes e descarte de campos pessoais antes da persistência;
- documentos escaneados dependerão de OCR auditável, mas OCR sozinho nunca será
  fundamento suficiente para publicar uma soma.
