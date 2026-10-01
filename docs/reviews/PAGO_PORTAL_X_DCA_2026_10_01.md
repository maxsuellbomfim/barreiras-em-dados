# Diferença entre o pago no portal e o pago declarado na DCA

Data: 2026-10-01. Situação: **fatos publicados; inferência e hipótese aguardam
revisão humana** (CLAUDE.md: conteúdo interpretativo além do registro oficial
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

Folha de pagamento publicada pela plataforma (`api.get_public_payroll_months_page`,
documentos mensais do TCM-BA; 2025 tem fevereiro a dezembro, janeiro ausente
na coleta):

| 2025 (11 meses) | Valor |
|---|---:|
| Bruto | R$ 407.147.687 |
| Descontos | R$ 138.065.416 |
| Líquido | R$ 269.082.271 |

Para comparação, no mesmo ano: DCA "Vencimentos" + "Contratação por Tempo
Determinado" = R$ 418.797.817 (12 meses); ordens de pagamento do portal com as
naturezas de vencimentos e de contratação temporária = R$ 282.708.740 (12 meses).

## Inferência (não publicada)

Comparando grupo a grupo, a diferença fica quase inteira em **pessoal**
(~R$ 113 mi em 2024 e ~R$ 133 mi em 2025); amortização fecha ao centavo e as
demais despesas ficam dentro de ±R$ 8 mi. A correspondência entre os textos de
natureza do portal e os códigos da DCA é aproximada (o portal usa plano local),
por isso esta leitura é inferência e não fato.

A folha reforça a leitura: as ordens de folha do portal ficam próximas do
**líquido** da folha (R$ 282,7 mi em 12 meses × R$ 269,1 mi em 11 meses), a
DCA fica próxima do **bruto** (R$ 418,8 mi × R$ 407,1 mi em 11 meses) e os
descontos da folha (R$ 138,1 mi em 11 meses) têm a ordem de grandeza da
diferença em pessoal (~R$ 133 mi). São fontes e recortes diferentes (meses,
órgãos, naturezas), então a correspondência não é exata.

## Hipótese (não publicada; exige revisão e, idealmente, pergunta à Prefeitura)

As ordens orçamentárias de folha no portal podem registrar o salário **líquido**,
enquanto as retenções (INSS do servidor, IR, consignações, pensão) seguem por
lançamentos extraorçamentários, ao passo que a DCA declara a folha **bruta**.
A ordem de grandeza dos empenhos extraorçamentários (~R$ 105 mi em 2025) é
compatível com parte da diferença, mas eles misturam retenções de fornecedores
e não foram ligados um a um à folha.

## Como confirmar (próximos passos sem acusação)

1. ~~Coletar a grade de pagamentos extraorçamentários do portal~~ — feito: o
   filtro existe, mas a fonte declara zero pagamentos extraorçamentários.
2. ~~Conferir a folha bruta mensal~~ — feito com a folha do TCM-BA (acima);
   falta preservar janeiro/2025 para fechar o ano.
3. Pedido via LAI/ouvidoria (texto abaixo), que é o único caminho para
   transformar a hipótese em fato declarado pela Prefeitura.

## Pedido de informação (LAI) — texto pronto para o titular enviar

Canal: e-SIC/ouvidoria da Prefeitura Municipal de Barreiras (Lei 12.527/2011).

> Assunto: Ordens de pagamento de folha no Portal da Transparência
>
> Com base na Lei nº 12.527/2011 (Lei de Acesso à Informação), solicito as
> seguintes informações sobre a despesa com pessoal publicada no Portal da
> Transparência do Município (consulta de despesas — pagamentos):
>
> 1. As ordens de pagamento orçamentárias referentes à folha (natureza
>    "Vencimentos e Salários" e "Contratação por Tempo Determinado") são
>    publicadas pelo valor bruto ou pelo valor líquido pago aos servidores?
> 2. As retenções da folha (contribuição previdenciária do servidor, imposto de
>    renda retido, consignações em favor de bancos, pensão alimentícia e
>    contribuições sindicais) são registradas e publicadas como lançamentos
>    extraorçamentários? Em qual consulta do Portal da Transparência elas podem
>    ser vistas? Observo que a consulta de pagamentos tem o filtro "Tipo da
>    Despesa: Extra - Orçamentária", mas ela não retorna nenhum pagamento em
>    dezembro de 2025 nem em agosto de 2026.
> 3. Em 2025, a Prefeitura declarou ao Tesouro Nacional, na DCA (Anexo I-D),
>    R$ 328.961.134,90 pagos no elemento 3.1.90.11 (Vencimentos e Vantagens
>    Fixas – Pessoal Civil). Qual é o valor total, no mesmo exercício, das
>    ordens de pagamento publicadas no portal para esse elemento, e qual é o
>    valor total das retenções correspondentes?
> 4. Há outras despesas pagas em 2025 que constam da DCA mas não são publicadas
>    na consulta de pagamentos do portal? Se houver, quais e por quê?
>
> Peço que a resposta seja enviada em formato eletrônico e, se possível, com
> os dados em planilha aberta (CSV ou XLSX).

## O que foi publicado

- `/financas/quem-recebe`: pago e liquidado do portal; comparação total com a
  DCA (cobertura e diferença, sem causa); tabela literal da DCA por grupo de
  natureza (`api.get_public_dca_expense_groups`), com aviso de que os grupos
  do portal não usam o mesmo código.
