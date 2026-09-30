# Amostra anotada da extração de atos do Diário (act-quality-sample/1.0.0)

Criada em 28/09/2026 pela migration `20260928164436_act_quality_sample`.
Mede precisão e revocação das regras que extraem **nomeações** e
**exonerações** (`gazette-act-candidates`) dos PDFs do Diário Oficial.

## Unidade e universo

- **Unidade:** a página do PDF oficial. O revisor confere uma página por vez.
- **Universo:** páginas com texto das 444 edições em PDF próprio da Prefeitura
  que já passaram pela extração (as cópias erradas servidas pelo catálogo,
  4309 e 4263 de 2024, ficam fora). Edições que só existem como texto do
  Querido Diário (47 dos 1.355 atos) não têm página e ficam fora.
- **Página de cada ato:** o texto canônico da edição é remontado a partir de
  `raw.document_pages` (texto embutido, ou OCR quando o embutido falta ou é só
  o número da página, unidos por linha em branco) e só é aceito quando o
  SHA-256 bate com `canonical_text_sha256` do ato. Na criação: 0 edições sem
  hash conferido e 0 atos sem página.

## Estratos e sorteio

| Estrato | Critério | Universo | Amostra |
|---|---|---:|---:|
| act_embedded | página com ato extraído, texto do PDF | 158 | 20 |
| act_ocr | página com ato extraído, OCR | 733 | 20 |
| keyword_embedded | sem ato, texto contém `nome[ai]` ou `exoner`, texto do PDF | 58 | 20 |
| keyword_ocr | idem, OCR | 402 | 20 |
| other_embedded | demais páginas, texto do PDF | 4.808 | 20 |
| other_ocr | demais páginas, OCR | 16.930 | 20 |

Sorteio determinístico: ordem por `sha256(semente:hash do PDF:página)` dentro
do estrato, semente `barreiras-act-quality-2026-09-28`. São 120 páginas de 90
edições (2021–2026), com 65 atos extraídos.

## Anotação

Aba **Qualidade dos atos** do admin, só para revisores ativos. Para cada ato
extraído da página: **Certo** (tipo, pessoa e cargo conferem), **Incompleto**
(é o ato, mas falta ou erra um campo) ou **Errado** (não é o ato, ou é do tipo
trocado). Depois, a contagem de nomeações e exonerações da página que não foram
extraídas. A anotação fica em `editorial.act_quality_annotations`
(append-only; a mais recente de cada página vale) e **não** altera
`editorial.editorial_reviews`, ou seja, não muda o que está publicado.

**Conferência por IA (ADR 0091).** O workflow `annotate-act-quality.yml`
envia a imagem da página do PDF oficial e a lista de atos a um modelo de visão
(`act-quality-prompt/1.0.0`). A resposta só é gravada se passar na validação
do contrato; o autor fica `ai:<modelo>:<versão do prompt>`, com o SHA-256 da
resposta. Uma anotação humana posterior na mesma página prevalece.

## Métricas (act-quality-metrics/1.1.0)

`api.get_act_quality_metrics(p_source)` aceita `any` (padrão), `human` ou
`ai`. Números vindos da IA são **estimativa automática, não revisão humana**.

Cada página conferida representa `universo / conferidas` páginas do seu estrato.

- Precisão estrita = certos / julgados; precisão ampla = (certos + incompletos) / julgados.
- Revocação = achados / (achados + não extraídos), com achado = certo ou incompleto.
- Recortes: todos os atos, nomeação e exoneração, por estrato e ponderado.

## Limitações

- Estratos grandes com poucas páginas (other_ocr: 1 página ≈ 846) tornam a
  revocação sensível: um único ato perdido ali pesa muito. É o preço de não
  esconder o que o OCR pode ter perdido; se a variância for alta, amplia-se a
  amostra desse estrato com nova versão.
- A regra só extrai nomeação e exoneração; outros atos de pessoal (designação,
  cessão) não entram na medição.
- Só 5 dos 65 atos da amostra estão publicados hoje; a medida é da extração,
  não só do que está no ar.
