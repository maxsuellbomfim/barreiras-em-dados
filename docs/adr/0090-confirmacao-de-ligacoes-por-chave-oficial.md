# ADR 0090 — Confirmação de ligações empenho → contrato por chave oficial

## Status

Aceita em 30/09/2026 pelo titular ("pode seguir com a confirmação por chave"),
que pediu automatizar o que dependia de decisão humana.

## Contexto

A regra do ADR 0086 confirmou 21.121 ligações empenho → contrato e deixou
6.518 citações para revisão humana (ADR 0088): 6.385 com o favorecido do
empenho escrito diferente do contratado e 133 com o número apontando para
mais de um contrato. O empenho do sistema da Prefeitura (WebRun) não traz
CNPJ, mas traz o **código do credor** (`field1144633`); o contrato do portal
traz o **CNPJ** (`documento`). As ligações confirmadas pela regra exata
mostram qual código de credor corresponde a qual CNPJ.

## Decisão

1. **Mapa código do credor → CNPJ**, derivado só das ligações `ligado` da
   regra exata (`commitment-contract-link/1.0.0`). Um código só entra no mapa
   se todas as suas ligações exatas apontarem para um único CNPJ.
2. **Confirma** a citação pendente quando exatamente um contrato candidato
   tem o CNPJ do credor. **Rejeita** quando nenhum candidato tem esse CNPJ
   (o contrato citado é de outra empresa). Os demais casos (credor fora do
   mapa, credor com mais de um CNPJ, vários candidatos com o mesmo CNPJ)
   continuam pendentes e não são publicados.
3. A decisão é gravada em `editorial.editorial_reviews` com o autor
   `automated:commitment-creditor-key`, o motivo e a evidência (código do
   credor, CNPJ, número de ligações exatas que o sustentam) — o mesmo caminho
   da publicação automática verificada do ADR 0012. A fila humana já exclui
   itens decididos.
4. A projeção pública rotula essas ligações como `creditor_key` ("confirmada
   por chave oficial"), distinta de `automated` (regra exata) e `human`.
5. A função `finance.confirm_commitment_links_by_creditor_key`
   (`commitment-creditor-key/1.0.0`) roda depois de cada ligação de
   empenhos, no workflow de empenhos. Retirada (`withdrawn`) continua valendo.

## Consequências

- Medição de 30/09: 1.812 citações confirmadas e 387 rejeitadas por chave;
  ~4.300 continuam pendentes por falta de código de credor no mapa.
- Próximo passo: completar o mapa com outras fontes oficiais que tragam o
  mesmo credor com CNPJ (pagamentos, PNCP), sem heurística de nome.
- Nenhum modelo de IA participa; a decisão é por igualdade de chaves.
