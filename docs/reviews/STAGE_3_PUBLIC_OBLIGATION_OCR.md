# Revisão operacional — OCR de pagamentos de restos a pagar

Data da revisão: 11 de agosto de 2026.

## Escopo

Validar os balancetes oficiais de janeiro e fevereiro de 2026 sem escrever no
banco. Esses PDFs apresentam o `Demonstrativo de Despesa Extra` rotacionado e o
texto embutido não preserva as linhas da tabela.

## Controles exercitados

- bytes restaurados do Storage conferidos contra tamanho e SHA-256 catalogados;
- OCR Tesseract em português, `PSM 6`, somente nas duas páginas da seção;
- orientações controladas e rastreadas;
- corte obrigatório antes de `TRANSFERÊNCIA FINANCEIRA`;
- valores convertidos em `Decimal`, sem LLM e sem ponto flutuante;
- identidade obrigatória: anterior + mês = acumulado;
- `dry_run=True`: nenhuma publicação e nenhuma falha persistida.

## Evidência remota

Workflow: [run 31541652327](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31541652327).

| Competência | Páginas | Rotação | Anterior | No mês | Acumulado |
|---|---:|---:|---:|---:|---:|
| janeiro de 2026 | 79–80 | 270° | R$ 0,00 | R$ 22.135.713,16 | R$ 22.135.713,16 |
| fevereiro de 2026 | 74–75 | 270° | R$ 22.135.713,16 | R$ 13.800.485,81 | R$ 35.936.198,97 |

O acumulado de fevereiro, R$ 35.936.198,97, coincide com o campo anterior do
registro de março já publicado. Essa continuidade é uma verificação adicional;
a fonte primária de cada mês continua sendo seu próprio PDF e hash.

## Limites e próximo gate

Os valores representam pagamentos de restos a pagar, não o saldo da dívida
municipal. O ensaio não publicou dados. Após a mesclagem, o workflow deve ser
executado em lotes idempotentes e as duas linhas precisam ser conferidas na RPC
pública e na página de finanças antes de ampliar o backfill para 2021.
