# Especificação: publicação automática de receitas financeiras

**Data:** 2026-08-02  
**Status:** aprovada; primeira implementação em revisão  
**Escopo:** primeiro relatório municipal de receitas e seu backfill histórico

## 1. Objetivo

Publicar automaticamente valores de receitas públicas municipais quando eles
forem extraídos de um documento oficial preservado e passarem por validações
determinísticas. A inteligência artificial poderá classificar o relatório,
localizar rótulos e produzir explicações em linguagem simples, mas não poderá
calcular, completar ou substituir valores.

O desenho deverá permitir que as regras sejam flexibilizadas no futuro por
versão de metodologia, sem reescrever o histórico nem apagar a versão anterior.

## 2. Resultado público esperado

Na página `/financas`, cada série publicada exibirá:

- período de referência e órgão;
- valor bruto, deduções e valor líquido quando disponíveis;
- unidade monetária e precisão usada;
- documento original e hash do PDF preservado;
- versão do parser, validador e metodologia;
- explicação assistida, claramente marcada como explicação;
- cobertura e limitações da fonte.

Ausência de valor será apresentada como “não informado pela fonte”, “não
extraído com segurança” ou “fora da cobertura”, nunca como zero.

## 3. Fluxo de dados

```text
raw.raw_artifacts (PDF filho preservado)
        |
        v
classificador determinístico + IA assistiva
        |
        v
extração determinística versionada
        |
        v
validação estrutural, monetária e de reconciliação
        |
        +--> falha: status needs_source/needs_review, sem publicação
        |
        v
finance.revenues + evidence.evidence_items
        |
        v
api pública + explicação assistida
```

O JSON municipal continuará sendo o registro pai. O PDF será o artefato filho
que sustenta a extração. Toda linha normalizada manterá vínculo com ambos.

## 4. Critérios para publicação automática

Uma linha poderá ser publicada automaticamente somente quando todos os itens
abaixo forem verdadeiros:

1. o artefato é de host permitido e possui hash SHA-256 verificado;
2. o tipo do relatório e o período foram identificados;
3. o parser reconhece o layout e sua versão está registrada;
4. o valor foi lido literalmente, sem conversão por ponto flutuante;
5. códigos e rótulos obrigatórios não estão duplicados;
6. a quantidade de páginas observada corresponde à esperada, quando aplicável;
7. totais e subtotais reconciliam dentro da regra publicada;
8. órgão, ano e período são compatíveis com o documento;
9. não existe conflito de fonte não resolvido;
10. a linha é idempotente e não cria uma segunda versão silenciosa.

Falhas de evidência não serão convertidas em zero. A linha ficará fora da
projeção pública até ser reprocessada ou explicitamente revisada.

## 5. Papel da IA em cascata

As etapas de IA serão opcionais, observáveis e versionadas:

- classificar RREO, RGF, demonstrativo de receita ou outro relatório;
- localizar o rótulo de uma linha no texto canônico;
- sugerir uma explicação curta para a população;
- apontar campos que precisam de fonte adicional.

A saída da IA deverá conter âncora literal no texto. Um validador rejeitará
qualquer número que não exista no trecho de evidência. A IA não poderá fazer
aritmética, inferir receita zero, criar período ou preencher lacunas.

## 6. Estados de processamento

Os estados públicos e internos serão separados:

- `collected`: documento preservado;
- `classified`: tipo e período identificados;
- `extracted`: linhas determinísticas produzidas;
- `validated`: checks aprovados;
- `published`: linha exposta na API pública;
- `needs_source`: falta documento, página ou campo essencial;
- `needs_review`: conflito ou ambiguidade exige decisão editorial;
- `superseded`: nova versão substituiu a anterior, que permanece consultável.

`assisted_enrichment` será tratado como um tipo de sugestão interna, não como
status de fila. Ele não poderá, sozinho, manter um candidato indefinidamente
na fila nem ser exibido como se fosse evidência.

## 7. Backfill histórico

O backfill inicial tentará cobrir 2021 até o presente em janelas limitadas,
respeitando rate limit, retries, circuit breaker e idempotência. Cada janela
registrará:

- início e fim solicitados;
- períodos encontrados;
- períodos sem documento;
- falhas de fonte;
- artefatos preservados;
- versão do parser e metodologia.

O portal exibirá uma faixa de cobertura para que “não encontrado” não seja
interpretado como “não existiu”.

## 8. Flexibilização futura

Regras poderão ser alteradas somente por uma nova versão de metodologia. Cada
versão deverá documentar:

- checks adicionados ou removidos;
- fixtures usadas;
- taxa de aprovação automática;
- falsos positivos e falsos negativos conhecidos;
- impacto sobre dados já publicados.

Uma flexibilização não reescreverá silenciosamente as linhas anteriores. A
revalidação criará novas versões e manterá o histórico de decisões.

## 9. Segurança e editorial

- valores financeiros são fatos derivados de documentos, não conclusões;
- anomalias serão publicadas como sinais com método e evidência;
- nenhuma pessoa ou empresa será acusada automaticamente;
- CPF completo e dados sensíveis permanecerão fora da camada pública;
- toda explicação assistida terá link para a fonte original;
- a administração poderá retirar temporariamente uma projeção defeituosa, mas
  deverá preservar o registro e criar uma decisão auditável.

## 10. Verificação e testes

Antes da publicação desta etapa:

- fixture sanitizada do primeiro relatório;
- testes de valores brasileiros sem `float`;
- testes de deduplicação, página e reconciliação;
- teste de hash e vínculo pai/filho;
- teste de resposta da API pública;
- teste de explicação sem número inventado;
- teste de replay idempotente;
- teste de backfill com janela vazia e janela parcial.

## 11. Fora do escopo desta etapa

- acusação ou classificação de corrupção;
- ranking de agentes públicos;
- publicação automática de patrimônio ou processos como conclusão;
- extração de todos os tipos de despesa;
- integração simultânea das dezenas de bases externas listadas;
- flexibilização dos critérios antes de observar resultados em produção.

## 12. Próximo passo

Implementar o parser e o publicador do primeiro relatório de receitas, usando o
artefato financeiro já preservado, seguido de um PR separado para revisão.

## 13. Primeira implementação

A primeira implementação desta especificação está sendo entregue separadamente
e inclui o contrato `public-revenue-pdf/1.0.0`, a migration de proveniência e o
workflow `Publicar receitas financeiras validadas`. A ativação em produção deve
começar com `limit=1`; somente depois de conferir o primeiro PDF o backfill deve
ser ampliado por ano.
