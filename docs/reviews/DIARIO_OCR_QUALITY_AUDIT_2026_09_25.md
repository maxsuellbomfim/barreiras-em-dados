# Auditoria por amostragem do OCR do Diário — 25/09/2026

Somente leitura: nenhum dado foi alterado. Revisão visual feita pelo agente de
engenharia, não por revisor humano registrado; serve para orientar correções,
não para certificar fidelidade.

## Amostra

- Universo: 16.877 páginas com `extraction_method = 'ocr'`
  (`gazette-ocr-text/1.0.0`), 350 PDFs. 16.741 páginas ligadas a uma edição.
- 30 páginas sorteadas de forma reproduzível (`order by md5(document_pages.id)`
  dentro de cada ano), estratificadas: 2021 (3), 2023 (3), 2024 (14), 2025 (4),
  2026 (6).
- Cada PDF foi baixado da fonte e conferido pelo SHA-256 preservado; a página
  foi renderizada (`pypdfium2`, escala 2) e comparada ao texto OCR.
- 30 páginas auditadas. Na primeira rodada, a edição 4213/2024
  (`referencia=13284`) pareceu servir outro arquivo. Era um download
  cortado do nosso lado (1,85 MB de 20,4 MB). Baixada de novo, o SHA-256
  bate com o preservado (`8110c515…`) e a página entrou na amostra.
- Todas as 30 páginas tinham só o número da página como texto embutido,
  confirmando que o OCR era necessário.

## Resultado

| Aspecto | Resultado na amostra |
|---|---|
| Texto corrido (atos, portarias, editais) | Fiel na maioria das páginas, com erros isolados de caractere. Nomes de pessoas, matrículas, inscrições, notas e classificação conferidos sem erro (4071 p.169, 4325 p.7, 4213 p.29). |
| Valores monetários em tabelas | Os valores conferidos batem: 12/12 (3349 p.13), 14/14 (3349 p.76), totais das linhas 3/3 (4088 p.54) e 1/1 (4147 p.46). |
| Estrutura de tabelas | Frágil. A associação código/descrição/valor se desalinha (3349 p.13 e p.23, 4323 p.70). Em células altas, número do item, quantidade, marca e preço unitário somem na maioria das linhas; o total da linha sobrevive (4088 p.54). |
| Dígitos | Houve erros que mudam o sentido: "2023" lido como "2028" duas vezes numa página limpa (4068 p.9); "25G" lido como "256" (4147 p.46); CNPJs em letra miúda de digitalização ruim (4608 p.27). |
| Símbolo `§` | **Erro sistemático.** Nenhuma página OCR contém `§`; ele vira `8` ("§2º" → "82º"). 2.163 páginas OCR têm o padrão "art. N … 8Nº". |
| Marcadores de lista | Numerais romanos e letras trocados (I→l, II→ll ou H, IX→TX, g)→E), l)→D)). |
| Faixa do cabeçalho (edição/data) | Ausente ou truncada em cerca de metade das páginas. Sem impacto: edição e data vêm do catálogo. |
| CPF mascarado pela fonte | **Não confiável.** Em "***.***.895-60" os asteriscos viram dígitos ou lixo ("+*4,449.895-60"); em 4325 p.7, cerca de 7 de 10 linhas. 1.285 páginas OCR contêm máscara `***`. O OCR pode gerar sequências com cara de CPF que não existem na fonte. |

## Achado de privacidade (fora do OCR)

Na página 4608 p.27, a própria fonte oficial publica o CPF completo de um
representante de empresa. Em seguida foi medida a projeção pública
(versões atuais de `editorial.gazette_document_versions`, servidas por
`api.get_integral_gazette_edition`, `api.get_integral_gazette_editions*` e
`api.search_integral_gazette_editions`):

- 712 de 6.588 documentos atuais, em 260 de 676 edições, contêm **3.093
  sequências no formato `000.000.000-00`**;
- a maior parte vem de texto embutido publicado pela prefeitura, não do OCR
  (nas páginas brutas: 25.126 ocorrências em texto embutido e 2.079 no OCR).

Isso contraria a regra "não publicar CPF completo" (`CLAUDE.md`,
`docs/COMPLIANCE_GATES.md`). A correção exige mascarar CPF em todas as saídas
públicas do Diário, incluindo a busca, sem alterar o bruto. Correção em PR
próprio: `editorial.mask_cpf_v1` gera `public_full_text`, e as RPCs públicas
passam a usá-lo. Na medição de 25/09, foram 4.870 máscaras em 906 documentos
atuais, sem CPF no formato estrito remanescente. Formas muito quebradas pelo
OCR, sem rótulo "CPF" próximo, podem escapar da regra.

## Comparação de modelos do Tesseract (25/09)

As 30 páginas foram reprocessadas localmente com Tesseract 5.4, na mesma
resolução da produção (300 dpi), em quatro configurações. Foram usadas 35
checagens pontuais tiradas da imagem: valores, datas, nomes, CNPJ e `§`.
"Modelo rápido" é o `tessdata_fast`, equivalente ao da produção. "Modelo
preciso" é o `tessdata_best`, 8,2 MB, SHA-256 `711de9db…`.

| Configuração | Tempo | `§` corretos | "art. N, 8Nº" | Letras acentuadas | Checagens |
|---|---|---|---|---|---|
| `por`, modelo rápido | 48 s | 0 | 6 | 1.739 | 25/35 |
| `por`, modelo preciso | 88 s | 0 | 2 | 1.772 | 28/35 |
| `por+eng`, modelo rápido | 59 s | 1 | 6 | 1.672 | 26/35 |
| `por+eng`, modelo preciso | 96 s | 8 | 0 | 1.630 | 30/35 |

- O modelo `por` não tem `§` no conjunto de caracteres: nenhuma das duas
  versões o emite. A precisa às vezes escreve "S4º" no lugar de "84º".
- O modelo preciso corrigiu "2023"/"2028" (4068 p.9) e "25G" (4147 p.46), sem
  perda de acentos. Custa cerca de 1,85 vez o tempo.
- `por+eng` resolve o `§`, mas tira o acento de 112 palavras ("Física" →
  "Fisica", "SAÚDE" → "SAUDE", "não" → "nao"). Isso prejudica a busca e a
  fidelidade. Descartado.

## Recomendações

1. **Privacidade:** feito em 25/09 (PR #829, migration `20260925121627`).
   Confirmado pela API anônima: nenhum CPF completo nas saídas, e a busca
   por CPF volta vazia.
2. **`§` e dígitos (decidido em 25/09):** o OCR do Diário passa a usar o
   modelo `por` preciso (tessdata_best, commit `9ddc24e7`, SHA-256
   `711de9db…`), gravado como `gazette-ocr-text/1.1.0`, mas só nas páginas
   ainda não lidas. As 16.877 páginas já lidas continuam na versão 1.0.0. O
   `§` fica apenas documentado; não há correção por regra.
3. **Tabelas:** não usar o texto OCR para extrair quantidade ou preço
   unitário sem revisão. O aviso de transcrição atual continua necessário.
4. **Máscara de CPF da fonte:** tratar como ilegível no texto OCR, e não como
   dado.

## Limites

- A amostra tem 30 páginas: estima tipos de erro, não taxa de erro com
  intervalo de confiança.
- A comparação cobriu principalmente o terço superior de cada página e os
  valores numéricos visíveis nele.
- A contagem de CPF por regex inclui números que só têm o formato de CPF,
  como erros de OCR ou placeholders. Ela mede exposição potencial, não
  quantas pessoas são identificáveis.
