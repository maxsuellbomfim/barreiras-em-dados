# Folha de março de 2023: PDF com cabeçalho "Abril / 2023"

Decisão de 25/09/2026, delegada pelo titular do projeto ("deixo a seu cargo
decidir março de 2023"). Registrada em código como
`payroll-declared-month-exceptions/1.0.0`
(`ACCEPTED_DECLARED_MONTH_DIVERGENCES` em
`workers/normalization/src/barreiras_normalization/payroll_publisher.py`).

## O conflito

| PDF | Portal lista como | Cabeçalho "MÊS/ANO" | Emitido em | Vínculos | Bruto |
| --- | --- | --- | --- | --- | --- |
| `SERVIDORES040423145443.pdf` | março/2023 (`id_serv 90`) | Abril / 2023 | 04/04/2023 11:49 | 5.351 | R$ 22.151.510,45 |
| `SERVIDORES050523181136.pdf` | abril/2023 (`id_serv 91`) | Abril / 2023 | 05/05/2023 | 5.422 | R$ 23.375.273,52 |

Hash do PDF em questão:
`11a6f1365797c296bceb4471b5ec66f8922bb1a0599d5a4e97d22d0a595c15cb`.

## Evidência

1. O portal oficial publica o documento como a Relação de Servidores de
   março/2023. É o único PDF listado para março.
2. O rodapé do próprio PDF registra a emissão em 04/04/2023. A folha de abril
   ainda não podia estar processada nessa data; a de abril foi emitida em
   05/05/2023.
3. Nos 73 relatórios oficiais conferidos (2021 a 2026), nenhum foi emitido
   dentro do próprio mês de referência: todos saem de 1 a 7 meses depois.
   Tratar este PDF como abril seria a única exceção a esse padrão.
4. As contagens seguem a série: fevereiro 5.356, março 5.351, abril 5.422
   vínculos.

## Decisão

O documento é a folha de **março de 2023** com o cabeçalho digitado errado.
Os valores são publicados como estão no PDF, sem ajuste, e a página do mês
mostra o aviso de que o cabeçalho diz "Abril / 2023", com a justificativa.

A exceção vale só para este hash e para o par exato (catálogo março/2023,
cabeçalho abril/2023). Qualquer outro PDF com competência divergente continua
indo para revisão, como o de agosto/2026 listado também como julho, que foi
invalidado (`declared_month_mismatch`).

## Como reverter

Se a Prefeitura publicar outro documento para março/2023 ou corrigir o
cabeçalho, remover a entrada de `ACCEPTED_DECLARED_MONTH_DIVERGENCES` e de
`apps/web/lib/payroll-document-notes.mjs` e registrar a correção como nova
versão, sem apagar o agregado atual.
