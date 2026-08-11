# ADR 0045 — Busca global do Diário Oficial integral

## Status

Aceito

## Contexto

A busca anterior filtrava apenas as edições já carregadas no navegador. Isso
impedia encontrar um nome ou ato histórico sem percorrer páginas manualmente.

## Decisão

Adicionar uma RPC de busca literal, case-insensitive e paginada, limitada a
120 caracteres. O servidor filtra título e texto integral preservado e retorna
somente os documentos correspondentes dentro de cada edição. A interface usa
`q` na URL, mantém o termo ao trocar de página e continua oferecendo o texto
literal e seus hashes.

## Consequências

- A pesquisa alcança todo o acervo integral já publicado.
- Busca por termos não é interpretação semântica nem classificação por IA.
- A consulta usa `security definer` com limites explícitos; tabelas brutas não
  são expostas ao navegador.
- Índices de texto e busca por similaridade poderão ser avaliados depois, com
  benchmark antes de trocar a busca literal determinística.
