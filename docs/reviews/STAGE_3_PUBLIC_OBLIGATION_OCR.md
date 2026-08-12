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

## Divergência oficial entre abril e maio de 2025

O backfill controlado identificou uma diferença de R$ 726,84 entre dois
balancetes oficiais consecutivos. O documento de abril informa pagamentos
acumulados de restos a pagar de R$ 19.325.093,07. O documento de maio, embora
feche internamente, informa R$ 19.324.366,23 como acumulado anterior.

Essa diferença não é corrigida por aproximação, não é atribuída ao OCR e não é
publicada como um valor reconciliado. A metodologia
`public-obligations-balancete/1.5.3` passa a:

- preservar os dois valores e suas evidências em `evidence.source_conflicts`;
- registrar a competência de maio com estado `conflict`, sem validação
  editorial ou numérica;
- encerrar a tentativa como conflito conhecido, evitando retries infinitos;
- expor no portal uma explicação neutra com os dois valores e a diferença;
- ressaltar que divergência entre fontes não é prova de irregularidade.

O conflito permanece aberto até que uma retificação ou outra evidência oficial
permita reconciliar a sequência. Junho continua coerente com o acumulado
declarado em maio, mas não resolve retroativamente a diferença com abril.

## Separador de milhar reconhecido como vírgula — outubro de 2025

O [run 31612290536](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31612290536)
isolou o balancete oficial de outubro de 2025, preservado com SHA-256
`1782ee9d5b17316c712df7ad8535c70bcc63989b13d70b3f8ae4940d19ec8b6f`.
Nas páginas 72 e 73, o OCR em rotação de 270 graus reconheceu o último valor do
total como `19.859,849,88`: um ponto de milhar foi lido como vírgula.

A versão `public-obligations-balancete/1.5.4` normaliza esse erro somente quando
os grupos de milhar continuam tendo três algarismos. A publicação ainda exige
o rótulo de total, a fronteira da seção e a identidade aritmética exata; uma
linha que não fecha continua rejeitada. O
[dry-run 31614310804](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31614310804)
validou o artefato real sem escrever no banco: R$ 19.859.849,88 acumulados até
o mês anterior + R$ 0,00 pagos em outubro = R$ 19.859.849,88 acumulados até
31/10/2025. A versão do job também foi incrementada para permitir o replay
auditável da tentativa que havia falhado.

## Pontuação entre colunas e na fronteira — julho de 2023

O balancete oficial de julho de 2023 preservado com SHA-256
`e525be3a76b7532b9077e7480829a059f19246c6bdd9d4a0ae96139f13434aae`
publica o total de restos a pagar nas páginas 111 a 113. O texto embutido traz
um ponto isolado entre a primeira e a segunda coluna e um hífen após o título
`TRANSFERENCIA FINANCEIRA`. Esses sinais são elementos gráficos, não valores.

A versão `public-obligations-balancete/1.5.5` aceita apenas ponto, hífen ou
dois-pontos isolados nesses separadores. Permanecem obrigatórios o rótulo
`Total`, os três valores monetários e a igualdade exata entre o acumulado
anterior, o pagamento mensal e o acumulado atual. Resultados terminais de uma
versão anterior não bloqueiam o reprocessamento por uma metodologia nova; o
histórico anterior continua preservado e auditável.
