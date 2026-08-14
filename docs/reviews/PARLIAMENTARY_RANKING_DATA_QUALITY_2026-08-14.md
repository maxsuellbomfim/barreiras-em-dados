# Auditoria do ranking de emendas por legislatura — 14/08/2026

## Escopo e grão

O ranking público agrega uma linha por autoria individual e legislatura. A
posição estadual usa o valor autorizado na LOA da Bahia; a federal usa o valor
destinado a Barreiras nas fontes federais reconciliadas. Empenho, liquidação e
pagamento não alteram a posição.

A auditoria foi executada em modo de leitura sobre o banco de produção após a
mesclagem do PR 343. Foram verificados anos observados, valores, autorias,
evidências, duplicidades exatas e o resultado das RPCs públicas.

## Resultado executivo

| Dimensão | Resultado | Severidade |
| --- | --- | --- |
| Emenda estadual 5724/2026, Marcone Amaral | R$ 1.548.747 incluídos no ranking | Conforme |
| Total de Marcone Amaral para Barreiras em 2026 | R$ 7.449.799 em quatro emendas | Conforme |
| Duplicidades exatas no recorte estadual/federal | Nenhuma | Conforme |
| Evidência oficial das linhas ranqueadas | 100% das linhas observadas | Conforme |
| 20ª legislatura estadual | 2024, 2025 e 2026 observados | Cobertura anual observada |
| 19ª legislatura estadual | somente 2022 observado; 2020 e 2021 sem registros | Importante |
| 57ª legislatura federal | 2024 e 2025 observados; 2026 sem registros | Importante |
| 56ª legislatura federal | somente 2021 observado; 2020 e 2022 sem registros | Importante |

“Sem registros” não significa valor zero, ausência de emenda ou falha
comprovada da fonte. Significa somente que o acervo usado pelo ranking ainda
não contém contribuição individual elegível naquele ano.

## Conferência de Marcone Amaral

| Emenda | Objeto resumido da fonte | Autorizado para Barreiras |
| --- | --- | ---: |
| 5715/2026 | Apoio financeiro à assistência à saúde | R$ 5.162.490 |
| 5724/2026 | Ônibus rural escolar | R$ 1.548.747 |
| 5723/2026 | Trator agrícola e implementos | R$ 448.000 |
| 5716/2026 | Apoio a quadrilhas juninas | R$ 290.562 |
| **Total** | **Quatro emendas** | **R$ 7.449.799** |

As quatro linhas apontam para o PDF oficial da LOA 2026 preservado sob o hash
iniciado por `38758dfdff5c`. A emenda 5724 aparece na página 203.

## Causa do risco de interpretação

A RPC de cobertura anterior informava a quantidade de emendas e autores, mas
não enumerava os anos esperados e observados. Assim, um cartão podia exibir o
período completo da legislatura mesmo quando o ranking continha apenas um ano.
O cálculo estava correto sobre as linhas existentes, porém a interface não
permitia ao cidadão distinguir ranking integral de recorte parcial.

## Correção proposta

- publicar cobertura anual determinística por esfera e legislatura;
- exibir anos com registros e anos ainda não observados junto ao ranking;
- usar explicitamente “recorte parcial” quando faltar algum ano;
- manter a ressalva de que ano observado não prova completude do universo;
- manter `not_observed` distinto de zero e de ausência oficial comprovada.

## Próxima lacuna de dados

O próximo backfill deve priorizar 2020 e 2022 no histórico federal, 2020 e 2021
no histórico estadual e a confirmação da disponibilidade federal de 2026. Cada
ano deverá receber estado de cobertura próprio antes de o ranking ser descrito
como completo.
