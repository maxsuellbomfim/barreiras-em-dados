# Revisão da publicação de leis da Câmara

Data: 2026-08-02

## Escopo

A API de dados abertos da Câmara Municipal passa a ter uma coleta semanal dos
recursos `leis` e `indicacoes`, preservando cada resposta bruta antes da
projeção pública. A rota `/camara` exibe identificador/protocolo, título,
ementa, tipo, ano, data, autoria declarada, situação e arquivo quando a fonte
informa.

## Regras editoriais

- O portal não atribui autoria individual, partido ou mérito a uma lei ou
  indicação sem que a fonte traga esse vínculo explicitamente.
- A busca e os filtros funcionam apenas sobre registros preservados e
  publicados pela API.
- URL de arquivo só é exibida quando começa com `https://`.
- Dados ausentes permanecem como “não informado”; não são convertidos em
  zero.
- A página é um registro documental, não uma avaliação da Câmara ou de seus
  membros.

## Operação

- Workflow: `.github/workflows/collect-camara-laws.yml`.
- Fonte: Portal de dados abertos da Câmara Municipal de Barreiras.
- Projeção: `api.get_camara_legislative_items`.
- Retenção: bruto e hash seguem as regras gerais de evidência do monorepo.

## Verificações previstas

- migration/seed reaplicáveis;
- build e typecheck do portal;
- `npm test` e `git diff --check`;

## Resultado da primeira coleta em producao

A execucao manual de 02/08/2026 preservou 8 paginas e 400 registros no
Supabase. A requisicao seguinte expirou na fonte municipal; os artefatos e
registros ja preservados nao foram desfeitos. O workflow foi ajustado para
registrar esse caso como coleta parcial quando houver pelo menos uma pagina
persistida, mantendo falha para indisponibilidade inicial ou erro de contrato.
- workflow com credenciais técnicas já existentes, sem segredo no YAML.

## Atividade legislativa e cobertura

O workflow usa uma matriz `leis`/`indicacoes` para que a falha de um recurso
não apague o outro. Antes da primeira execução de `indicacoes`, a página
exibirá apenas as leis já preservadas; isso significa coleta pendente, não
ausência de indicações.
