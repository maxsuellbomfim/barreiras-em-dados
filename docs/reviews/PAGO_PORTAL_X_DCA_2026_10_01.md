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

## Inferência (não publicada)

Comparando grupo a grupo, a diferença fica quase inteira em **pessoal**
(~R$ 113 mi em 2024 e ~R$ 133 mi em 2025); amortização fecha ao centavo e as
demais despesas ficam dentro de ±R$ 8 mi. A correspondência entre os textos de
natureza do portal e os códigos da DCA é aproximada (o portal usa plano local),
por isso esta leitura é inferência e não fato.

## Hipótese (não publicada; exige revisão e, idealmente, pergunta à Prefeitura)

As ordens orçamentárias de folha no portal podem registrar o salário **líquido**,
enquanto as retenções (INSS do servidor, IR, consignações, pensão) seguem por
lançamentos extraorçamentários, ao passo que a DCA declara a folha **bruta**.
A ordem de grandeza dos empenhos extraorçamentários (~R$ 105 mi em 2025) é
compatível com parte da diferença, mas eles misturam retenções de fornecedores
e não foram ligados um a um à folha.

## Como confirmar (próximos passos sem acusação)

1. Coletar a grade de **pagamentos extraorçamentários** do portal, se existir,
   e somar por mês as retenções de folha.
2. Conferir no RREO (Anexo 1/2) e nos documentos mensais do TCM-BA já
   coletados se a folha bruta mensal bate com a DCA.
3. Pedido via LAI/ouvidoria: "as ordens de pagamento de folha publicadas no
   portal são pelo valor líquido?".

## O que foi publicado

- `/financas/quem-recebe`: pago e liquidado do portal; comparação total com a
  DCA (cobertura e diferença, sem causa); tabela literal da DCA por grupo de
  natureza (`api.get_public_dca_expense_groups`), com aviso de que os grupos
  do portal não usam o mesmo código.
