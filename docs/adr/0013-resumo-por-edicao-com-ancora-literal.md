# 0013 — Resumo por edição com âncora literal verificada

Data: 2026-08-01. Status: aceita (ratificada pelo titular no merge deste PR).

## Contexto

A missão é traduzir e publicar tudo o que sai no Diário Oficial, não só
atos de pessoal. A extração estruturada cresce tipo a tipo, mas o cidadão
precisa de cobertura completa desde já. O ADR 0012 estabeleceu o padrão:
publicação automática apenas do que o código consegue verificar contra o
documento oficial.

## Decisão

Cada edição direta preservada ganha um **resumo item a item** gerado pela
cascata de IA (ADR 0011), sob o mesmo princípio do ADR 0012 adaptado a
conteúdo generativo:

1. O texto canônico da edição é fatiado e a IA lista os atos publicados,
   cada item com tipo, título, resumo simples e uma **citação literal**
   ("âncora") copiada do texto.
2. O verificador `edition-digest-anchor-check/1.0.0` só aceita itens cuja
   âncora ocorre literalmente no texto (mesma normalização do ADR 0012).
   Item sem âncora verificável é descartado — nunca publicado.
3. O resumo aprovado entra na trilha de `editorial_reviews` como
   publicação automática (auditável, reversível por withdraw) e é
   projetado em `/diario` com rótulo de IA, link para o PDF oficial,
   hash e canal de correção.
4. Cobertura parcial (fatias demais ou fatia com contrato violado) é
   marcada `partial` e exibida como "resumo parcial" — nunca silenciosa.

## Limites aceitos

- Título e resumo são generativos: fiéis por construção de prompt e
  ancoragem, mas não literalmente verificáveis; o rótulo público e a
  reversão auditada carregam esse risco, aceito pelo titular (01/08/2026).
- Edições do Querido Diário (texto .txt) ficam para uma fatia futura; a
  fonte primária (coletor direto) é coberta primeiro.
- A fila humana não exibe resumos como cartões; a reversão vive no
  histórico, como qualquer publicação automática.
