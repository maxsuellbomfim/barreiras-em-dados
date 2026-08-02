# Revisão da aplicação das migrations em produção

Data: 2026-08-02

## Resultado

As três projeções públicas foram aplicadas com sucesso ao projeto Supabase
`Barreiras em Dados` (`mpladsyzilmgiefejpkq`):

- `public_state_representatives`;
- `public_tse_barreiras_votes`;
- `public_camara_laws`.

As funções `api.get_state_representatives`,
`api.get_tse_barreiras_votes` e `api.get_camara_laws` existem e possuem
`EXECUTE` para `anon`. A consulta de fumaça retornou zero leis porque o
workflow da Câmara ainda não populou `municipal_transparency_leis`; isso não é
interpretado como ausência de leis.

## Correção de compatibilidade

O banco de produção já possuía IDs de endpoints criados por migrations
anteriores. As migrations locais foram ajustadas para não depender de UUIDs
fixos: fontes são encontradas por `slug`, endpoints usam `id` gerado e a
idempotência é garantida pela chave `(data_source_id, slug)`.

## Segurança

- nenhum dado foi apagado ou atualizado em tabelas brutas;
- as funções continuam com `search_path` vazio e grants explícitos;
- os advisors do Supabase foram executados após a alteração.

Os advisors também exibem alertas informativos preexistentes de RLS sem
política em schemas internos e o aviso de proteção contra senhas vazadas
desativada no plano atual; nenhum desses alertas foi criado por esta migration.
