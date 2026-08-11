# ADR 0058 — Pagamentos de restos a pagar no balancete

## Status

Aceita em 11 de agosto de 2026.

## Contexto

O `Demonstrativo de Despesa Extra` do balancete municipal apresenta uma linha
agregada de `RESTOS A PAGAR`, com o valor pago até o mês anterior, o valor pago
no mês e o valor acumulado até o mês. A extração textual de PDFs rotacionados
pode inverter a ordem visual dessas colunas.

Esses números não representam o saldo da dívida municipal. Publicá-los como
“dívida” ou somá-los novamente à despesa paga no mês produziria uma leitura
incorreta para a população.

## Decisão

O Barreiras 360 publicará essa linha como pagamentos de restos a pagar:

- o período virá dos metadados oficiais do balancete, não de inferência livre;
- a extração será determinística, com `Decimal`, e exigirá uma única seção
  inequívoca de `RESTOS A PAGAR`;
- a publicação exigirá `pago anteriormente + pago no mês = pago acumulado`;
- o registro normalizado manterá o artefato PDF exato, sua URL e seu SHA-256;
- respostas de API, páginas HTML ou artefatos reconciliados incorretamente não
  poderão substituir o PDF na linhagem;
- o portal destacará o valor pago no mês e recolherá acumulados, metodologia e
  hash em um detalhe expansível;
- a interface dirá expressamente que o valor não é a dívida total nem informa
  quanto ainda falta pagar.

Falhas de hash, ambiguidade, extração ou aritmética serão registradas na fila de
processamento e farão o job terminar com erro visível. A indisponibilidade da
explicação assistida por IA não impedirá a publicação do fato validado.

### Adendo: PDFs rotacionados

Balancetes cujo texto embutido não preserva a linha da tabela usam fallback OCR
Tesseract em português, restrito à página da seção `RESTOS A PAGAR` e à sua
continuação. O extrator testa orientações fixas, mantém a fronteira anterior a
`TRANSFERÊNCIA FINANCEIRA` e só aceita um resultado aritmeticamente fechado.

Método, versão do OCR, páginas e rotação entram no localizador da evidência.
Uma divergência aritmética encontrada no texto embutido não aciona OCR. O
workflow oferece ensaio explícito sem persistência para validar um novo layout
contra o PDF oficial antes de autorizar a publicação.

## Consequências

A população passa a enxergar um fluxo de caixa relevante de compromissos de
períodos anteriores sem confundi-lo com estoque de dívida. O primeiro registro
é uma base verificável para o backfill mensal desde 2021.

O saldo de restos a pagar, empréstimos, precatórios e dívida consolidada
continuará pendente até que cada família documental tenha contrato, fonte e
reconciliação próprios.

## Verificação

- teste do parser com linha representativa do PDF oficial;
- teste contra o PDF real de junho de 2026;
- teste de idempotência e falha de hash do publicador;
- teste PGlite de aritmética, privilégios e vínculo com o PDF exato;
- contrato estrito da RPC e teste de linguagem pública;
- testes Python, Node, typecheck, build, Ruff e segurança.
- ensaio remoto sem escrita nos PDFs oficiais de janeiro e fevereiro de 2026.
