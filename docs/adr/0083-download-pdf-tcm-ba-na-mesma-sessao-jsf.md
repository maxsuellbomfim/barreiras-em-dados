# ADR 0083 — Download do PDF do TCM-BA na mesma sessão JSF

## Status

Aceito em 27 de agosto de 2026.

## Contexto

O botão público do e-TCM não aponta diretamente para o arquivo. O clique faz
um POST AJAX autenticado pela sessão JSF, recebe um XML com a instrução
`window.open('/epp/PdfReadOnly/downloadDocumento.seam')` e só então permite o
GET do PDF. Abrir o endereço final fora dessa sessão pode devolver conteúdo
incorreto ou expirado.

## Decisão

O coletor recompõe a competência e a página exata do catálogo, compara total e
metadados com o snapshot preservado, aciona o formulário daquele documento e
baixa o binário na mesma sessão. O fluxo aceita somente o host e o endpoint
oficiais, HTTP 200, `application/pdf`, assinatura `%PDF-` e marcador `%%EOF`.
HTML, XML inesperado, mudança do catálogo ou endereço divergente bloqueiam a
coleta. Catálogo e PDF possuem limites de tamanho separados.

## Consequências

- posição global, página e documento precisam concordar antes do clique;
- o XML preparatório e o PDF ficam disponíveis para preservação auditável;
- um workflow verde não poderá tratar página de sessão expirada como PDF;
- o download em massa continuará bloqueado até a persistência filha e o gate
  físico serem comprovados com uma amostra pequena.
