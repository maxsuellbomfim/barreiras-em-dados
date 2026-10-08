# ADR 0096 — Citações de contrato em empenhos sem correspondência na lista do portal

## Status

Aceita em 08/10/2026 pelo titular, com publicação condicionada: a página só
mostra dados depois que um revisor ativo conferir uma amostra no portal e
registrar a aprovação (`api.review_contract_citation_comparison`).

## Contexto

Os empenhos do sistema de despesas (WebRun) citam no histórico o contrato que
os sustenta ("Contrato nº 338/2020"). A regra determinística do ADR 0086 marca
como `nenhum_contrato` a citação cujo número não existe na lista de contratos
publicada pelo próprio portal (API de dados abertos, recurso `contratos`).

Medição de 08/10/2026:

- a lista tem 1.517 contratos e foi lida inteira (offsets 0 a 1.500; a última
  página tem 17 itens), mais antigo de 2015;
- 7.156 citações de empenhos de 2024–2026 (fora a Câmara) apontam ~425
  contratos sem correspondência; 394 citações têm contrato com o mesmo número
  e o mesmo fornecedor no PNCP;
- nenhuma citação "sem correspondência" tem o mesmo número com outro sufixo
  (`-FMS`) e o mesmo fornecedor na lista (2.045 casos de mesma numeração são
  de outros fornecedores).

Os ADRs 0087 e 0088 mantinham essas citações internas. A revisão editorial
de 08/10 classificou a comparação como sinal do tipo anomalia (resultado de
regra, não texto literal) com risco reputacional para fornecedores nomeados.

## Decisão

1. **Comparação, não acusação.** Título: "Citações de contrato em empenhos:
   comparação com a lista de contratos do portal". Cada linha diz: "número
   citado sem correspondência exata na lista lida em DD/MM/AAAA
   (contract-citation-comparison/1.0.0)". Aviso fixo: pode ter sido publicado
   com outro número, em outro portal, como aditivo, ata, convênio ou
   credenciamento, ou ainda não ter sido publicado; não indica irregularidade.
2. **Só o pago.** Empenhado não é somado (ADR 0095 1.3.0: o portal não publica
   anulações). O valor é a soma exata das ordens de pagamento ligadas aos
   empenhos pela chave oficial.
3. **PNCP é categoria à parte.** Mesmo número de contrato e mesmo fornecedor
   (chave de grafia do ADR 0094 entre o credor do empenho e o fornecedor do
   PNCP) vira "publicado no PNCP", com link, e não entra em "sem
   correspondência".
4. **Pessoa física sem nome.** Credor que não é entidade
   (`finance.payment_creditor_is_entity_v1`) entra só no agregado por órgão,
   sem nome, sem número de contrato, sem trecho e sem chave do empenho.
5. **Escopo.** Câmara Municipal fica fora (publica contratos em portal próprio,
   não coletado), pelo órgão do empenho. Só empenhos orçamentários.
6. **Sem ranking.** Ordem por órgão e data, não por valor.
7. **Portão de publicação.** `api.get_public_contract_citations` devolve só o
   estado `awaiting_review` até existir aprovação registrada para a versão
   1.0.0. A amostra de conferência (`api.get_contract_citation_review_sample`,
   só revisor ativo) tem 20 casos de semente fixa mais os dois exemplos da
   medição. Nova versão da regra exige nova aprovação.
8. Canal público de correção e direito de resposta da Prefeitura e dos
   fornecedores na página.

## Falsos positivos declarados

Sufixo de órgão escrito de outro jeito; erro de digitação no histórico;
aditivo, apostila ou termo citado como contrato; ata de registro de preços,
convênio, credenciamento SUS ou consórcio; contrato de outro ente; contrato
encerrado retirado da lista; defasagem entre o empenho e a leitura da lista.
