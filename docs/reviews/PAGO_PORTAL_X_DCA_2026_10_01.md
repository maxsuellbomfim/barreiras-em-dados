# Diferença entre o pago no portal e o pago declarado na DCA

Data: 2026-10-01 (teste mensal na mesma noite). Situação: **fatos
publicados; inferência e hipótese aguardam revisão humana** (CLAUDE.md: conteúdo interpretativo além do registro oficial
não é publicado sem revisão registrada).

## Pergunta

Por que as ordens de pagamento orçamentárias publicadas no portal da Prefeitura
somam menos que o "pago" que a própria Prefeitura declarou ao Tesouro na DCA?

## Fatos (registros oficiais, já publicados ou conferíveis)

Fontes: DCA do SICONFI, Anexo I-D, coluna "Despesas Pagas" (raw
`siconfi_dca_line`, coleta de 24/08/2026); ordens de pagamento do portal
(`municipal_payment_webrun`, grade mais recente de cada mês, só orçamentárias,
régua `municipal-payment-recipients/1.3.0`).

| | 2024 | 2025 |
|---|---:|---:|
| Pago declarado na DCA (total) | R$ 908.142.035,95 | R$ 950.096.510,57 |
| Pago nas ordens orçamentárias do portal | R$ 800.954.319,11 | R$ 807.188.271,59 |
| Diferença | R$ 107.187.716,84 | R$ 142.908.238,98 |

Por grupo da DCA (pago):

| Grupo DCA | 2024 | 2025 |
|---|---:|---:|
| 3.1 Pessoal e Encargos Sociais | R$ 429.233.233,02 | R$ 499.801.753,51 |
| 3.3 Outras Despesas Correntes | R$ 305.592.408,96 | R$ 300.039.250,55 |
| 4.4 Investimentos | R$ 87.542.263,31 | R$ 47.738.429,02 |
| 4.5 Inversões Financeiras | R$ 1.817.522,53 | R$ 3.510.986,15 |
| 4.6 Amortização da Dívida | R$ 83.956.608,13 | R$ 99.006.091,34 |

Somas do portal:

- grupo "dívida" do portal (amortização, juros e correção): R$ 83.956.608,13
  (2024) e R$ 99.006.091,34 (2025) — **iguais ao centavo** à linha 4.6 da DCA
  nos dois anos;
- grupo "pessoal" do portal mais as naturezas de INSS/previdência patronal:
  R$ 316.148.420 (2024) e R$ 366.581.581 (2025);
- natureza "VENCIMENTOS E SALÁRIOS" no portal em 2025: R$ 203.423.432; a DCA
  declara R$ 328.961.134,90 em "3.1.90.11 Vencimentos e Vantagens Fixas";
- o portal publica, na grade de empenhos, empenhos do tipo
  "Extra-Orçamentária" de 2025 que somam ~R$ 105 mi pelo valor original
  (retenções da folha, consignações, INSS e IR retidos de fornecedores,
  pensão alimentícia); a grade de pagamentos coletada não traz nenhuma linha
  extraorçamentária (todas as 53.731 linhas de 2024–2026 são "Orçamentária").

Sondagem da consulta de pagamentos do portal (formulário 7910, 01/10/2026):

- o formulário tem o filtro "Tipo da Despesa" com as opções
  "Extra - Orçamentária" (E) e "Orçamentária" (O), enviado à regra
  `TRP_TRANSP_PAGAMENTO_MODIFICAR_CONSULTA` no parâmetro `P_4`;
- com `P_4=O`, agosto/2026 devolve as mesmas 1.799 ordens (R$ 46.118.304,88)
  da consulta sem filtro;
- com `P_4=E`, a fonte declara **zero** pagamentos em agosto/2026 e em
  dezembro/2025: o portal não publica pagamentos extraorçamentários, embora a
  consulta de empenhos traga empenhos extraorçamentários de retenção da folha.

Folha de pagamento dos servidores municipais (PDF oficial "Listagem Sintética
E-TCM" publicado no portal mtransparente da Prefeitura):

- fevereiro a dezembro/2025 vêm da projeção pública
  (`api.get_public_payroll_months_page`);
- janeiro/2025 tem um único PDF oficial que traz `1-Normal, 4-Adiant. 13º` no
  mesmo documento (SHA-256 `d2345bdb…5190ac9`). Pelo ADR 0074 ele fica fora da
  página da folha (não é folha regular separável), mas seus totais foram
  extraídos e validados pela aritmética do próprio documento
  (`hr.payroll_report_aggregates`, parser 1.2.0, invalidação
  `mixed_payroll_cycle_header`). Para uma soma **anual**, que já inclui o 13º,
  o documento inteiro conta.

| 2025 | Fev–dez | Janeiro (documento misto) | Ano |
|---|---:|---:|---:|
| Bruto | R$ 407.147.687 | R$ 25.196.820,48 | R$ 432.344.508 |
| Descontos | R$ 138.065.416 | R$ 8.788.468,04 | R$ 146.853.884 |
| Líquido | R$ 269.082.271 | R$ 16.408.352,44 | R$ 285.490.623 |

Para comparação, no mesmo ano: DCA "Vencimentos" + "Contratação por Tempo
Determinado" = R$ 418.797.817; ordens de pagamento do portal com as naturezas
de vencimentos e de contratação temporária = R$ 282.708.740.

Mês a mês (teste de 01/10/2026, noite). "Pago no portal" = ordens
orçamentárias com data de pagamento no mês e natureza `3.7.6.8.0 VENCIMENTOS E
SALÁRIOS`, `3.7.6.2.0 OUTRAS CONTRATAÇÕES POR TEMPO DETERMINADO` ou `3.7.5.6.0
SALÁRIO CONTRATO TEMPORÁRIO`; bruto e líquido da folha regular do mesmo mês
(`api.get_public_payroll_months_page`). Valores em R$ milhões:

| Mês | Bruto | Líquido | Pago no portal | Portal ÷ líquido | Portal ÷ bruto |
|---|---:|---:|---:|---:|---:|
| fev/2025 | 28,24 | 18,73 | 21,37 | 1,14 | 0,76 |
| mar/2025 | 30,45 | 20,44 | 21,79 | 1,07 | 0,72 |
| abr/2025 | 33,17 | 22,46 | 23,04 | 1,03 | 0,69 |
| mai/2025 | 32,77 | 22,21 | 23,00 | 1,04 | 0,70 |
| jun/2025 | 44,92 | 34,13 | 22,93 | 0,67 | 0,51 |
| jul/2025 | 32,51 | 21,77 | 22,51 | 1,03 | 0,69 |
| ago/2025 | 33,60 | 22,69 | 22,59 | 1,00 | 0,67 |
| set/2025 | 35,47 | 24,01 | 23,79 | 0,99 | 0,67 |
| out/2025 | 35,22 | 23,78 | 23,00 | 0,97 | 0,65 |
| nov/2025 | 35,48 | 23,89 | 24,25 | 1,02 | 0,68 |
| dez/2025 | 65,33 | 34,98 | 35,47 | 1,01 | 0,54 |
| jan/2026 | 36,93 | 25,08 | 24,75 | 0,99 | 0,67 |
| fev/2026 | 33,78 | 22,99 | 22,84 | 0,99 | 0,68 |
| mar/2026 | 35,80 | 24,42 | 24,04 | 0,98 | 0,67 |
| abr/2026 | 37,12 | 25,91 | 22,15 | 0,86 | 0,60 |
| mai/2026 | 36,55 | 25,41 | 22,52 | 0,89 | 0,62 |
| jun/2026 | 34,83 | 24,26 | 25,80 | 1,06 | 0,74 |
| jul/2026 | 34,97 | 24,55 | 25,11 | 1,02 | 0,72 |

Agosto/2026 ficou fora: a grade de pagamentos de setembro ainda está
incompleta e a folha de agosto é paga parte em setembro.

Empenhos **extraorçamentários** de 2025 na grade de empenhos do portal
(classificação aproximada pelo texto do histórico e pelo credor; estornos são
linhas negativas separadas):

| Grupo (pelo histórico) | Linhas | Soma |
|---|---:|---:|
| Retenção da folha repassada a bancos (consignados) | 808 | R$ 40.605.842,48 |
| INSS do servidor retido na folha | 1.456 | R$ 33.062.979,06 |
| Proventos/salário-família lançados como extraorçamentários | 963 | R$ 14.316.129,64 |
| Retenções de fornecedores (INSS/DARF de notas fiscais) | 623 | R$ 12.952.543,95 |
| Outras retenções da folha | 521 | R$ 3.042.191,57 |
| Contribuição sindical retida na folha | 377 | R$ 2.566.533,25 |
| Demais | 864 | R$ 1.992.422,33 |
| Estornos | 252 | −R$ 3.595.852,06 |

Ou seja: as retenções da folha **aparecem como empenhos** extraorçamentários
(cerca de R$ 79 mi em 2025 nos quatro grupos de folha), mas nenhuma ordem de
**pagamento** extraorçamentária é publicada (filtro `P_4=E` devolve zero).

## Inferência (não publicada)

Comparando grupo a grupo, a diferença fica quase inteira em **pessoal**
(~R$ 113 mi em 2024 e ~R$ 133 mi em 2025); amortização fecha ao centavo e as
demais despesas ficam dentro de ±R$ 8 mi. A correspondência entre os textos de
natureza do portal e os códigos da DCA é aproximada (o portal usa plano local),
por isso esta leitura é inferência e não fato.

A folha do ano inteiro reforça a leitura:

- as ordens de folha do portal (R$ 282,7 mi) ficam a **1%** do **líquido** da
  folha (R$ 285,5 mi);
- a DCA (R$ 418,8 mi) fica a 3% do **bruto** da folha (R$ 432,3 mi);
- os descontos da folha (R$ 146,9 mi) têm a ordem de grandeza da diferença em
  pessoal (~R$ 133 mi).

São fontes e recortes diferentes (o PDF da folha cobre os servidores
municipais; a DCA usa elementos de despesa; o portal, naturezas locais), então
a correspondência não é exata e continua sendo inferência.

O teste mensal torna a leitura **forte**: em 12 de 18 meses o pago no portal
fica a ±4% do líquido da folha, no mesmo mês (inclusive dezembro, com 13º), e
em nenhum mês chega perto do bruto (51% a 76%). Seis meses fogem do padrão sem
explicação nos dados: fev–mar/2025 acima do líquido (talvez resíduo do ciclo
misto de janeiro), jun/2025 abaixo (adiantamento de 13º possivelmente pago por
outra via, como os "proventos" extraorçamentários), abr–mai/2026 abaixo e
jun/2026 acima.

## Hipótese (não publicada; exige revisão e, idealmente, pergunta à Prefeitura)

As ordens orçamentárias de folha no portal registram o salário **líquido**;
as retenções seguem por empenhos extraorçamentários (visíveis no portal); a
DCA declara a folha **bruta**. Os empenhos de retenção da folha (~R$ 79 mi) não
cobrem todos os descontos da folha (R$ 146,9 mi); o restante pode incluir o IR
retido na fonte, que pertence ao próprio Município (CF, art. 158, I) e por isso
não é repassado a terceiros, e a pensão alimentícia. Isso não foi verificado.

O ponto que os dados públicos **não** respondem: se os empenhos de retenção
foram efetivamente pagos (repassados ao INSS, aos bancos e aos sindicatos), e
quando, porque o portal não publica ordens de pagamento extraorçamentárias.

## Como confirmar (próximos passos sem acusação)

1. ~~Coletar a grade de pagamentos extraorçamentários do portal~~ — feito: o
   filtro existe, mas a fonte declara zero pagamentos extraorçamentários.
2. ~~Conferir a folha bruta mensal~~ — feito com os PDFs oficiais da folha,
   ano inteiro de 2025 (janeiro pelo documento misto, só na soma anual).
3. ~~Testar mês a mês~~ — feito: o portal acompanha o líquido (ver tabela).
4. Pedido via LAI/ouvidoria (texto abaixo). Já não é preciso perguntar se o
   portal publica bruto ou líquido; a pergunta útil é **se e quando as
   retenções foram repassadas**, o que os dados públicos não mostram.

## Pedido de informação (LAI) — texto pronto para o titular enviar

Canal: e-SIC/ouvidoria da Prefeitura Municipal de Barreiras (Lei 12.527/2011).

> Assunto: Repasse das retenções da folha de pagamento em 2025
>
> Com base na Lei nº 12.527/2011 (Lei de Acesso à Informação), solicito
> informações sobre as retenções da folha de pagamento dos servidores
> municipais no exercício de 2025.
>
> No Portal da Transparência, a consulta de empenhos traz empenhos do tipo
> "Extra-Orçamentária" com histórico de retenção da folha (contribuição
> previdenciária do segurado ao INSS, consignações em favor de bancos e
> contribuições sindicais). Já a consulta de pagamentos, com o filtro "Tipo da
> Despesa: Extra - Orçamentária", não retorna nenhum pagamento (por exemplo,
> em dezembro de 2025 e em agosto de 2026). Por isso solicito:
>
> 1. Os valores efetivamente repassados em 2025, mês a mês, ao INSS
>    (contribuição do segurado retida na folha), a cada instituição
>    financeira (consignações) e a cada entidade sindical, com a data de cada
>    repasse.
> 2. O valor total do imposto de renda retido na fonte sobre a folha em 2025,
>    mês a mês, e a forma como ele foi contabilizado.
> 3. Em qual consulta do Portal da Transparência os pagamentos
>    extraorçamentários (repasses de retenções) podem ser vistos e, se não
>    forem publicados, o motivo.
> 4. A confirmação de que as ordens de pagamento orçamentárias da folha
>    publicadas no portal correspondem ao valor líquido pago aos servidores.
>
> Peço que a resposta seja enviada em formato eletrônico e, se possível, com
> os dados em planilha aberta (CSV ou XLSX).

## O que foi publicado

- `/financas/quem-recebe`: pago e liquidado do portal; comparação total com a
  DCA (cobertura e diferença, sem causa); tabela literal da DCA por grupo de
  natureza (`api.get_public_dca_expense_groups`), com aviso de que os grupos
  do portal não usam o mesmo código.
- A tabela mensal e a leitura "portal = líquido" **não** foram publicadas:
  aguardam revisão humana registrada.
