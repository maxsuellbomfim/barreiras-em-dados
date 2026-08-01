# 0012 — Publicação automática verificada por código, revisão por exceção

Data: 2026-08-01. Status: aceita (ratificada pelo titular no merge deste PR).

## Contexto

A visão da plataforma é traduzir e publicar tudo o que sai no Diário
Oficial, em linguagem que qualquer pessoa entenda. O fluxo da etapa 1C
exigia aprovação humana individual antes de qualquer publicação. Na
prática, o titular é o único revisor e não pode aprovar item a item todos
os dias; o portão humano virou o gargalo que impede a plataforma de
cumprir a própria missão.

Ao mesmo tempo, as regras inegociáveis existem por bons motivos: LLMs
alucinam, atos de pessoal citam pessoas reais e um erro publicado tem
custo reputacional e legal (LGPD, dano moral).

## Decisão

Publicação automática passa a existir, mas **somente para conteúdo que o
código consegue verificar literalmente contra o documento oficial**:

1. A extração determinística e a IA assistida propõem valores de campos.
2. Um verificador determinístico e versionado
   (`gazette-act-verifier/1.0.0`) confere cada valor contra o trecho
   oficial: um valor só é aceito se ocorrer literalmente no texto
   (normalizado por espaços/caixa; datas conferidas por extenso e nos
   formatos usuais). Valor sugerido pela IA que não está no texto é
   descartado — nunca publicado.
3. Um candidato só é publicado automaticamente quando o essencial está
   verificado: pessoa, número e data da Portaria, e existe resumo
   assistido em linguagem simples. Caso contrário permanece na fila para
   decisão humana.
4. A publicação automática é registrada em
   `editorial.editorial_reviews` com `reviewer_subject`
   `automated:gazette-act-verifier` e checklist contendo os valores
   verificados e a origem de cada um (determinística ou assistida) —
   mesma trilha de auditoria, mesma reversão (`withdraw`) humana.
5. O site rotula cada ato com o modo de revisão: "revisado por pessoa"
   ou "publicação automática verificada por código, sujeita a
   correção". O canal público de correção segue valendo para tudo.

A revisão humana muda de portão para **exceção**: a fila concentra apenas
o que o código não conseguiu verificar; o histórico permite reverter
qualquer publicação automática; e a amostragem periódica (gate 1B da
amostra anotada) mede a taxa de erro do verificador.

## O que NÃO muda

- O resumo assistido continua rotulado como gerado por IA.
- Achados de anomalia, inferências além do registro oficial e qualquer
  conteúdo interpretativo continuam exigindo revisão humana prévia.
- Bruto append-only, hashes, versões e evidência por registro.
- LLMs continuam sem calcular totais e sem decidir publicação: quem
  decide é o verificador determinístico, que é código versionado.

## Consequências

- O rótulo público diferencia explicitamente os dois modos; retirar um
  ato automático é um clique auditado no admin.
- Falso positivo do extrator que passe pela verificação literal (ex.:
  bloco em maiúsculas que não é nome) publicaria um dado errado, porém
  fiel ao texto oficial; mitigação: exigência de portaria+data+pessoa
  em conjunto, stoplist institucional, canal de correção e reversão.
- O risco residual foi aceito pelo titular em 01/08/2026 ao priorizar
  cobertura e tempestividade com interferência humana mínima.
