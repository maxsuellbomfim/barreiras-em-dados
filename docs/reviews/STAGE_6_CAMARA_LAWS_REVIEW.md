# Revisão da publicação de leis da Câmara

Data: 2026-08-02

## Escopo

A API de dados abertos da Câmara Municipal passa a ter uma coleta semanal do
recurso `leis`, preservando cada resposta bruta antes da projeção pública. A
rota `/camara` exibe identificador, título, ementa, tipo, ano, data, status e
arquivo quando a fonte informa.

## Regras editoriais

- O portal não atribui autoria individual, partido ou mérito a uma lei sem que
  a fonte traga esse vínculo explicitamente.
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
- Projeção: `api.get_camara_laws`.
- Retenção: bruto e hash seguem as regras gerais de evidência do monorepo.

## Verificações previstas

- migration/seed reaplicáveis;
- build e typecheck do portal;
- `npm test` e `git diff --check`;
- workflow com credenciais técnicas já existentes, sem segredo no YAML.
