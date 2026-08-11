# ADR 0044 — Paginação pública do Diário Oficial integral

## Status

Aceito

## Contexto

O processamento integral preserva cada edição e seus documentos no Supabase,
mas a página pública não deve carregar todo o acervo em uma única resposta. Um
limite fixo de 40 edições fazia parecer que o backfill histórico não havia
funcionado, além de tornar a resposta HTML pesada.

## Decisão

Manteremos o RPC legado para compatibilidade e adicionaremos um RPC paginado,
com `page_size` e `page_offset`, ordenado pela edição mais recente. A interface
pública carregará 20 edições por vez e pedirá uma linha extra para determinar
se existem edições anteriores. A navegação será por URL (`pagina`), permitindo
compartilhar e auditar cada recorte sem expor as tabelas brutas.

## Consequências

- Edições históricas já persistidas tornam-se navegáveis sem aumentar
  indefinidamente o HTML inicial.
- A busca textual atual continua limitada à página aberta; uma busca global
  será uma etapa posterior com filtro no RPC e paginação própria.
- O RPC continua sendo `security definer`, com validação de limites e execução
  concedida somente às roles públicas necessárias.
