# Revisão operacional — OCR de pagamentos de restos a pagar

Data da revisão: 11 de agosto de 2026.

## Escopo

Validar os balancetes oficiais de janeiro e fevereiro de 2026 sem escrever no
banco. Esses PDFs apresentam o `Demonstrativo de Despesa Extra` rotacionado e o
texto embutido não preserva as linhas da tabela.

## Controles exercitados

- bytes restaurados do Storage conferidos contra tamanho e SHA-256 catalogados;
- OCR Tesseract em português, `PSM 6`, somente nas páginas não vazias
  entre o início da seção e `TRANSFERÊNCIA FINANCEIRA`;
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

## Ampliação histórica — balancetes de 2022

Em 12 de agosto de 2026, os cinco artefatos que falharam no primeiro ensaio de
2022 foram comparados com os respectivos PDFs oficiais, inclusive por
renderização visual das páginas do `Demonstrativo de Despesa Extra`.

| Competência | Diagnóstico da fonte | Tratamento determinístico |
|---|---|---|
| junho | total completo; rótulo extraído como `Tot a` | aceitar somente R$ 19.895.890,06 + R$ 588.494,89 = R$ 20.484.384,95 |
| julho | total completo precedido por pontuação de layout | aceitar somente R$ 20.484.384,95 + R$ 303.721,65 = R$ 20.788.106,60 |
| setembro | seção presente, mas o PDF termina sem total mensal e sem a fronteira `TRANSFERÊNCIA FINANCEIRA` | resultado terminal `incomplete_in_source_document`; não publicar valor nem registrar zero |
| novembro | total completo com espaços inseridos nos valores | remover apenas espaços internos e exigir R$ 21.214.414,18 + R$ 51.117,60 = R$ 21.265.531,78 |
| dezembro | continuação da seção após páginas vazias | localizar a próxima página com a fronteira e aplicar OCR apenas à página inicial e à continuação |

O total geral `Total Extra, Restos a Pagar e Transferência Financeira` não é
usado para reconstruir um total de restos a pagar ausente, pois mistura famílias
financeiras distintas. Linhas individuais que fecham aritmeticamente também não
substituem a linha `Total`, evitando publicar uma conta isolada como agregado.

A metodologia passa a `public-obligations-balancete/1.5.0`. A nova versão deixa
os jobs anteriormente falhos elegíveis para novo ensaio sem alterar ou apagar o
histórico de tentativas.

O primeiro ensaio remoto da versão, executado em 12 de agosto de 2026 sobre as
11 competências disponíveis de 2022, bloqueou a publicação porque o texto
embutido de junho separava o marcador `Tot a` dos valores e oferecia uma linha
de conta individual que também fechava aritmeticamente. O parser passou a tratar
essa grafia fragmentada como marcador obrigatório de total, impedindo o uso da
linha individual e encaminhando o documento ao layout estruturado. O próximo
ensaio permanece sem escrita e só libera publicação com zero falhas técnicas.
Essa correção é versionada como `public-obligations-balancete/1.5.1`, para que o
artefato recusado no primeiro ensaio possa ser reavaliado sem apagar a tentativa
anterior.

## Continuidade em três páginas — maio de 2024

O [run 31597824037](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31597824037)
publicou quatro de cinco artefatos e isolou o balancete de maio de 2024. A
renderização visual mostrou a seção começando na página 113, o total na
página 114 e a fronteira `TRANSFERÊNCIA FINANCEIRA` na página 115. O parser
anterior selecionava apenas as extremidades e, portanto, pulava a página que
continha o total.

A versão `public-obligations-balancete/1.5.2` inclui todas as páginas não
vazias dentro desse intervalo e continua ignorando páginas intermediárias em
branco. O PDF oficial foi validado localmente pelo texto de layout, sem LLM:
R$ 37.936.002,42 + R$ 4.487,11 = R$ 37.940.489,53. O novo job versionado permite
reprocessar a tentativa falha sem apagar o diagnóstico anterior.
