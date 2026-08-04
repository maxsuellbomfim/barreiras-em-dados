# Revisão da publicação de leis da Câmara

Data: 2026-08-04

## Escopo

A API de dados abertos da Câmara Municipal possui coleta semanal dos recursos
`leis` e `indicacoes`, preservando cada resposta bruta antes da projeção pública.
A rota `/camara` exibe identificador/protocolo, título, ementa, tipo, ano, data,
autoria declarada, situação e arquivo quando a fonte informa.

## Regras editoriais

- O portal não atribui autoria individual, partido ou mérito a uma lei ou indicação sem que a fonte traga esse vínculo explicitamente.
- A busca textual, o tipo, o ano e a autoria exata são aplicados no servidor sobre todo o acervo preservado.
- A paginação mantém os filtros ativos e nunca confunde ausência na página com ausência no acervo.
- URL de arquivo só é exibida quando começa com `https://`.
- Dados ausentes permanecem como “não informado”; não são convertidos em zero.
- A página é um registro documental, não uma avaliação da Câmara ou de seus membros.

## Operação

- Workflow: `.github/workflows/collect-camara-laws.yml`.
- Fonte: Portal de dados abertos da Câmara Municipal de Barreiras.
- Projeção paginada: `api.get_camara_legislative_page`.
- Retenção: bruto e hash seguem as regras gerais de evidência do monorepo.

## Verificações previstas

- migration/seed reaplicáveis;
- build e typecheck do portal;
- `npm test` e `git diff --check`;
- smoke test dos filtros no RPC com recortes de tipo, ano e texto.

## Resultado da primeira coleta em produção

A execução manual preservou páginas e registros no Supabase. Uma requisição
seguinte pode expirar na fonte municipal; os artefatos e registros já preservados
não são desfeitos. O workflow registra coleta parcial quando houver ao menos uma
página persistida, mantendo falha para indisponibilidade inicial ou erro de contrato.

## Atividade legislativa e cobertura

O workflow usa uma matriz `leis`/`indicacoes` para que a falha de um recurso não
apague o outro. A projeção pública usa 50 registros por página e devolve a
contagem total do recorte filtrado. O navegador recebe apenas a página corrente;
as barras de autoria são explicitamente uma amostra dessa página, não uma
contagem global.
