# Etapa 6 — Mapeamento de fontes de representação política

Levantamento em 01/08/2026. Todas as URLs foram testadas; status HTTP real.

## Câmara dos Deputados (federal) — FUNCIONA

- `https://dadosabertos.camara.leg.br/api/v2/deputados?siglaUf=BA` — JSON,
  sem chave, 39 deputados eleitos pela Bahia.
- Detalhe: `/api/v2/deputados/{id}` traz nome civil, nascimento,
  escolaridade, gabinete, foto oficial **e CPF** — o CPF é preservado no
  bruto e nunca projetado publicamente (ADR 0014).
- **Implementado nesta fatia.**

## Senado Federal — FUNCIONA (com ressalva)

- `https://legis.senado.leg.br/dadosabertos/senador/lista/atual` — XML,
  sem chave, devolve os 81 senadores. **Não há filtro por UF**
  (`/uf/BA` e `?uf=BA` não funcionam): filtrar por `UfParlamentar=BA`.
- Bahia hoje: Angelo Coronel (Republicanos) e Jaques Wagner (PT).
- Termos: "uso livre" genérico, sem licença explícita.

## Assembleia Legislativa da Bahia (ALBA) — SÓ HTML

- `https://www.al.ba.gov.br/deputados/deputados-estaduais` — sem JSON/CSV
  e sem portal de dados abertos. Estrutura raspável: nome, partido, foto e
  URL individual estável em `/deputados/deputado-estadual/{id}`.
- Consequência: deputados estaduais exigem raspagem versionada e
  tolerante a mudança de layout, com estado explícito de falha.

## TSE — FUNCIONA (arquivos grandes)

- Candidatos 2024:
  `https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip`
  — ZIP com CSV por UF, > 10 MB, licença CC-BY. Filtro de Barreiras pelo
  **código TSE do município**, não pelo nome.
- Votação nominal por município/zona 2024:
  `https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip`
  — ZIP/CSV, > 10 MB. **É esta a fonte do vínculo territorial** do ADR
  0014 (quantos votos cada candidato recebeu em Barreiras).
- Candidatos 2026: o pacote já existe mas contém apenas `leiame.pdf`
  (627 KB) — o registro de candidaturas ainda não fechou. Reverificar
  após o período de registro.
- `robots.txt` do portal bloqueia `/api/` e `/dataset/*/history`
  (Crawl-Delay 10); os arquivos em `cdn.tse.jus.br` não são bloqueados.
- Pendência antes de implementar: abrir o CSV real para fixar o
  dicionário de colunas.

## Câmara Municipal de Barreiras — MISTO

- **API JSON existe**:
  `https://portaldatransparencia.cmbarreiras.ba.gov.br/api?resource=leis&limit=5`
  devolve JSON real (`id_lei, data, tipo, titulo, ano_ref, informacoes,
  url, ativo`). Cobre contratos, licitações, servidores, leis, sessões.
- **Mas não há recurso `vereadores`**. A lista dos 21 vereadores só existe
  em HTML no domínio institucional `https://cmbarreiras.ba.gov.br/vereadores`.
- Licença não declarada na documentação do portal.

## Ordem recomendada de implementação

1. **TSE — votação nominal 2024**: maior valor (é o vínculo territorial
   mensurável do ADR 0014) e formato estável; exige pipeline de ZIP/CSV.
2. **Câmara dos Deputados**: feito nesta fatia.
3. **Senado**: baixo esforço (XML), completa a representação federal.
4. **Vereadores de Barreiras**: raspagem HTML; alto valor local.
5. **ALBA**: raspagem HTML, maior esforço.
6. **API da Câmara Municipal** (`?resource=`): útil para leis e contratos
   locais, não fecha a Etapa 6 sozinha.

## Secretários municipais

Já vêm do Diário Oficial pelo pipeline existente (nomeações e
exonerações). O dossiê de secretário se monta a partir dos atos
publicados, sem fonte externa nova.
