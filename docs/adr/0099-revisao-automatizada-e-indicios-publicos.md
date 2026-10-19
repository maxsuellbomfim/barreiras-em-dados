# ADR 0099 — Revisão automatizada e indícios públicos

## Status

Aceita em 19/10/2026 pelo titular: "a ideia da plataforma é ser anônima e
autônoma, não deveria depender de revisão humana, você pode fazer as
revisões. A plataforma tem que apontar os indícios de fraude, de corrupção e
facilitar o trabalho de quem quiser fiscalizar."

Substitui, onde conflitarem: ADR 0005 (fronteira reputacional), ADR 0018
(sinais só em triagem), a exigência de revisão humana dos ADR 0096 e 0097 e
as seções "Conteúdo reputacional", "Direito de resposta" e "Uso de IA" da
política editorial anterior.

## Contexto

A publicação de anomalias, achados reputacionais e casos de fila dependia de
revisão humana registrada. Na prática não havia revisor disponível: 14,3 mil
citações empenho→contrato, 160 apelidos, 116 sinais financeiros e a lista de
empresas recém-abertas ficaram parados ou foram publicados com rótulo de
triagem. O objetivo da plataforma é apontar onde olhar, de forma contínua e
sem depender de pessoas.

## Decisão

### 1. Revisão automatizada registrada substitui a revisão humana

Todo conteúdo que antes exigia revisão humana passa a exigir **revisão
automatizada registrada**, em duas camadas obrigatórias:

1. **Conferência por código** (determinística, versionada): o caso existe no
   documento oficial preservado (hash), os campos e valores batem com a fonte,
   a regra e o parâmetro estão registrados.
2. **Conferência por agente de IA**: lê o caso contra o documento oficial,
   procura explicação lícita comum e erro de dado, e decide `approved`,
   `rejected` ou `needs_more_evidence` com justificativa curta.

Publica só o que passar nas duas. A IA pode vetar e retirar; não pode
publicar o que o código não validou, nem calcular totais. Cada decisão grava
identidade do agente, modelo, versão do roteiro, entradas, evidência e data.
Na página, o rótulo é explícito: "Conferido automaticamente — sem revisão
humana". Uma pessoa pode revisar ou retirar qualquer item a qualquer tempo,
mas isso é opcional.

### 2. Indícios podem ser publicados

Uma anomalia pode ir ao ar como **indício** quando:

- a regra é determinística, versionada e foi medida em produção (resultado,
  limite de cobertura e taxa de falso positivo registrados no ADR da regra);
- cada caso passou pela revisão automatizada do item 1;
- a página mostra a regra, o parâmetro, o documento oficial, o limite de
  cobertura e as explicações lícitas comuns daquele padrão.

### 3. Linguagem: indício, nunca acusação

O site aponta fatos que merecem apuração. É proibido afirmar ou insinuar, em
título, texto, rótulo ou ordenação, que pessoa ou empresa identificada
cometeu crime, fraude, corrupção, desvio ou superfaturamento. Vocabulário
permitido: "indício", "alerta", "padrão de risco", "merece apuração",
"diverge da fonte". Esses termos descrevem o achado, não a conduta.

Motivo: afirmar crime sem condenação pode ser calúnia (Código Penal, art.
138); apontar um fato documentado com a fonte não é.

### 4. Contestação anônima com correção automática

Formulário público, sem login e sem exigir identificação, com protocolo e
estado. Cada contestação dispara nova conferência automatizada do caso. Se a
evidência não se sustentar, o item é retirado e uma nova versão marca a
supersessão. O histórico nunca é apagado.

### 5. Salvaguardas que continuam

- Regras determinísticas e versionadas; IA não calcula totais.
- Fato, inferência, indício e hipótese continuam como campos distintos.
- Nada de CPF completo nem dados pessoais desnecessários (razão social de MEI
  com CPF é mascarada).
- Mesma metodologia para todos os órgãos, gestões, partidos e fornecedores;
  nenhum filtro ou ranking por partido.
- Correções criam versões; histórico não é apagado.

## Consequências

- Filas humanas deixam de bloquear a publicação: sinais financeiros,
  contratos citados, empresas recém-abertas, citações empenho→contrato e
  apelidos passam pela revisão automatizada.
- Nova página pública de indícios reúne as regras publicadas, com filtro por
  órgão, fornecedor e período, evidência e método por caso.
- O risco jurídico não desaparece: a Constituição veda o anonimato na
  manifestação do pensamento (art. 5º, IV) e a LGPD exige controlador
  identificável. Antes do lançamento, recomenda-se parecer de advogado
  brasileiro sobre quem responde pela plataforma; isso não bloqueia o
  desenvolvimento.
