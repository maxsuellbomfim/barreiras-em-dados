# ADR 0087 — Publicação das ligações empenho → contrato

## Status

Aceita em 24/09/2026 por decisão do titular ("publique as ligações
confirmadas com rótulo").

## Contexto

O ADR 0086 define a regra determinística que liga um empenho a um contrato
municipal: citação literal do número no histórico escrito pela Prefeitura,
contrato único com esse número (sufixo de órgão e ano incluídos) e favorecido
igual ao contratado. A primeira execução (junho a agosto de 2026) produziu
1.531 ligações confirmadas a 185 contratos; uma amostra aleatória conferida
manualmente estava correta em todos os casos.

A ligação junta duas fontes oficiais, mas não interpreta nada: cada parte vem
literalmente de um registro preservado. O ADR 0012 já admite publicação
automática de conteúdo verificado por código, com rótulo e reversão auditada.

## Decisão

- Somente decisões `ligado` da versão vigente da regra são públicas.
  `citacao_sem_confirmacao`, `sem_citacao` e `fora_do_escopo` continuam
  internas; a fila de revisão humana decide as primeiras.
- A página mostra, em cada contrato municipal, os empenhos ligados com número,
  data, órgão, favorecido, tipo da nota e valor como **texto literal da
  fonte**, o trecho do histórico que cita o contrato e a evidência (hash da
  grade preservada e link da página oficial de despesas).
- O histórico completo do empenho não é publicado: ele pode mencionar pessoas
  e não é necessário para conferir a ligação.
- Nenhum total é calculado. Somar empenhos exige tratar anulações e reforços
  com metodologia própria; até lá, a lista é literal.
- Rótulo público: "Ligação automática verificada por código, sujeita a
  correção", com a explicação das três condições.
- Retirada: uma linha em `editorial.editorial_reviews` com
  `target_type = 'finance.commitment_contract_links'` e
  `decision = 'withdrawn'` remove a ligação da projeção sem apagar a decisão
  original.
- Só a versão mais recente de cada empenho aparece; versões anteriores ficam
  no acervo.

## Consequências

- O cidadão passa a ver, pela primeira vez, quais empenhos da Prefeitura
  saíram de cada contrato, com a prova de onde a ligação veio.
- Um erro de cadastro da própria fonte (número de contrato citado por engano)
  seria publicado fiel ao texto oficial; mitigação: rótulo, evidência, canal
  de correção e retirada auditada.
- Mudar a regra exige nova versão e atualização da projeção, nunca reescrita
  das decisões anteriores.
