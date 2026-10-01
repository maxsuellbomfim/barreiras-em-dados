# ADR 0095 — Quem recebe o dinheiro da Prefeitura

## Status

Aceita em 01/10/2026 pelo titular ("o cidadão precisa saber para onde é
destinado cada centavo"), com parecer contábil prévio (aceite condicionado,
condições cumpridas abaixo).

## Contexto

O portal da Prefeitura publica cada ordem de pagamento com data, valor, credor,
chave do empenho, órgão pagador e a descrição da natureza da despesa no plano
local (o código numérico não é o elemento padrão do MCASP). Somar por credor sem
contexto engana: em 2025 os maiores "credores" são a própria Prefeitura e o
FOPAG (repasse de folha), o INSS, a Receita Federal e a Caixa (dívida).

## Decisão

1. **Escopo**: apenas ordens orçamentárias, com chave `O-` e data do pagamento
   no ano pedido, na grade mais recente de cada mês. O que fica fora é
   contado (`year_excluded_rows`) e valor ilegível também (`year_unreadable_rows`).
   Inclui Câmara e fundos municipais, mostrados por órgão pagador.
2. **Grupo** por regra fixa sobre a descrição da natureza
   (`finance.payment_recipient_group_v1`, primeiro padrão vence): não
   identificado (vazio/"NÃO USAR"), sentenças judiciais, benefícios do servidor
   (antes de "PREVID"), dívida (`JUROS (SOBRE|DA)`, não juros de mora),
   encargos e tributos, pessoal, auxílios, transferências, restituições e
   ressarcimentos; o resto é "compras, obras, serviços e demais despesas".
3. **Nome do credor** só quando o nome traz forma jurídica, é ente público ou
   MEI (CNPJ-base no início) e não contém CPF
   (`finance.payment_creditor_is_entity_v1`). Pessoa física — servidor,
   beneficiário, locador ou prestador sem forma jurídica no nome — entra num
   agregado sem nome, em qualquer grupo. Sobrenome "Sá" não conta como "S.A."
   (corrigido antes da publicação).
4. **Restos a pagar** explícitos: soma paga a empenhos de anos anteriores, pela
   data do empenho coletado; o pago a empenhos fora da coleta (antes de 2024)
   aparece separado, sem ano inventado.
5. **Materialização**: o cálculo sobre a grade bruta leva ~10 s por ano (limite
   do papel anônimo: 3 s). `finance.compute_payment_recipients` é privada;
   `finance.refresh_payment_recipients` grava a tabela
   `finance.payment_recipient_snapshots`, com trava, auditoria e hash do
   conteúdo, ao fim do workflow de empenhos. `api.get_public_payment_recipients`
   só lê a tabela e informa `refreshed_at`.
6. Ressalvas obrigatórias na página: não é a "despesa paga" do RREO nem a
   despesa com pessoal da LRF; inclui restos a pagar; extraorçamentários fora;
   folha aparece como repasse à Prefeitura/FOPAG; grupos não indicam
   irregularidade.

## Consequências

- 2025: R$ 807.188.271,59 em 19.201 ordens; a soma dos grupos fecha com o total;
  R$ 19.018.753,03 de restos a pagar; Câmara R$ 23,6 mi.
- 96,8% do valor pago tem credor nomeado; o restante fica no agregado.
- Credores com nome limitados a 150 por grupo (o agregado e o total do grupo
  sempre aparecem).
- Pendente: ligar cada credor nomeado ao CNPJ do cadastro da Receita quando o
  empenho estiver ligado a contrato confirmado.

## Revisão 1.1.0 (01/10/2026)

Credor nomeado ganha CNPJ, razão social e natureza jurídica do cadastro da
Receita (ADR 0093) quando o empenho pago está ligado a contrato confirmado
(regra automática do ADR 0086 ou decisão aprovada vigente dos ADRs 0090/0094)
e todas as ligações do credor apontam o mesmo CNPJ. Nada é inferido pelo nome;
credor com ligações a CNPJs diferentes fica sem CNPJ. Na primeira atualização,
2025 teve 97 dos 210 credores listados com CNPJ (R$ 186,4 mi), sem nenhum
conflito de CNPJ.

## Revisão 1.2.0 (01/10/2026): nada fica de fora

- Todos os credores com nome aparecem (fim do limite de 150 por grupo).
- Pessoas físicas e credores sem forma jurídica são somados **por natureza da
  despesa** (ex.: locação de imóveis, serviços de terceiros PF), sem nomes.
- CNPJ também pelo código oficial do credor no sistema da Prefeitura (ADR 0090):
  quando esse código já está ligado, por contratos confirmados, a um único CNPJ
  do cadastro, os demais pagamentos do mesmo código herdam o CNPJ; continua
  exigido que tudo aponte o mesmo CNPJ.
- Conferência: a soma de todas as linhas publicadas é igual ao total do ano em
  2024, 2025 e 2026. 2025: 502 linhas nomeadas (248 com CNPJ, R$ 202,7 mi) e 44
  agregados de pessoas físicas por natureza.
- Sem CNPJ continuam os credores sem nenhum contrato confirmado (repasses de
  folha, INSS, Receita Federal, Caixa, concessionárias); não há campo de
  CNPJ no empenho nem no pagamento do portal.
- A atualização leva ~4–5 min (três anos); roda no workflow de empenhos com
  limite de 10 min.
- Antes de 2024 o portal devolve meses parciais com erro da própria fonte
  (ADR 0086); esse período fica fora até a fonte corrigir ou outra fonte
  oficial cobrir.
