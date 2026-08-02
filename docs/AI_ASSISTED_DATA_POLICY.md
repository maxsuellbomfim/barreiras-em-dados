# IA assistiva em cascata no Barreiras 360

## Escopo

A cascata de provedores pode auxiliar todos os domínios do portal: Diário
Oficial, finanças, licitações, contratos, folha, obras, representantes,
emendas e anomalias. Ela é uma camada de leitura, classificação, explicação e
triagem. Não é a autoridade do dado.

## Regra para números

Nenhum modelo calcula total, percentual, média, ranking, saldo ou comparação.
Os valores entram no sistema por fonte bruta preservada e passam por código
determinístico com `Decimal`, schemas, reconciliação e testes. A IA pode sugerir
qual campo parece corresponder a uma coluna ou explicar um resultado já
calculado; a sugestão precisa apontar para um trecho literal e permanece como
`needs_review` até ser validada.

## Cascata

1. Groq, quando houver chave e modelo disponível;
2. OpenRouter, limitado a modelos gratuitos;
3. Gemini, como último nível;
4. estado explícito `assisted_inference_unavailable` quando todos falharem.

Cada tentativa registra provedor, modelo, prompt, versão, hash da entrada,
resposta bruta, status e custo conhecido. Chaves vivem somente no worker; o
browser nunca chama um provedor diretamente.

## Tarefas permitidas

| Domínio | Assistência permitida | Autoridade final |
|---|---|---|
| Diário | recompor texto, classificar ato, resumir | trecho e revisão |
| Finanças | reconhecer tipo de relatório, sugerir colunas, explicar | parser e `Decimal` |
| Licitações | classificar modalidade e extrair objeto sugerido | contrato e documento |
| Representantes | organizar fontes e explicar indicadores | registros oficiais |
| Obras | classificar etapa e resumir documento | medição, contrato e fonte |
| Anomalias | priorizar triagem e explicar regra acionada | regra determinística |

## Bloqueios

- não inventar campo ausente;
- não preencher CPF, valor, data ou vínculo por contexto;
- não declarar ilegalidade, corrupção ou culpa;
- não publicar automaticamente uma conclusão reputacional;
- não aceitar uma cifra sem ocorrência literal no documento ou sem cálculo
  determinístico reproduzível;
- não ocultar indisponibilidade de provedor.

O contrato financeiro inicial está em
`workers/document-processing/src/barreiras_docproc/financial_assist.py`.
Ele valida âncora literal de cada linha e rejeita qualquer valor que não
esteja no trecho recebido.
