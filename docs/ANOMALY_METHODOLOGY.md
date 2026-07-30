# Metodologia de anomalias

## Estado

Detecção de anomalias está **desativada** na etapa inicial. Este documento define
as condições para implementá-la sem produzir acusações automáticas.

## Definição

Uma anomalia é o resultado reprodutível de uma regra versionada aplicada a um
conjunto de dados com população, período e comparabilidade declarados. Ela pode
indicar erro de fonte, erro de parser, caso legítimo incomum ou necessidade de
investigação. Não prova irregularidade.

## Contrato de uma regra

Cada `anomaly_rule` deve ter:

- código e versão imutável;
- título e descrição neutros;
- domínio e campos usados;
- pré-condições de qualidade;
- população e exclusões;
- unidade, período e denominador;
- expressão/implementação determinística;
- limiar e justificativa;
- severidade operacional, não reputacional;
- evidências requeridas;
- testes e fixtures;
- limitações e falsos positivos conhecidos;
- owner e aprovação metodológica.

## Contrato de um achado

Um `anomaly_finding` registra:

- regra/versão e timestamp de execução;
- dataset snapshot ou query hash;
- valores de entrada e saída em JSON tipado;
- fatos/evidências que o sustentam;
- estados de qualidade e conflito;
- explicações alternativas;
- estado de triagem e revisão;
- decisão editorial separada.

Reexecutar uma regra não substitui o achado anterior.

## Comparabilidade mínima

Comparações de itens só são permitidas após normalizar:

- descrição e especificação;
- material/serviço;
- unidade e conversão;
- quantidade;
- período e índice de preços, quando aplicável;
- modalidade e condições;
- local de entrega/execução;
- marca/modelo ou equivalência;
- frete, impostos e composição do lote;
- qualidade e tamanho da população.

Itens não comparáveis recebem esse estado; não são forçados à categoria
“outlier”.

## Fluxo

1. validar qualidade e cobertura;
2. executar regra determinística;
3. gerar achado interno;
4. revisar erro de coleta/parser primeiro;
5. reconciliar fontes e contexto;
6. revisão técnica especializada;
7. revisão legal/editorial quando houver impacto reputacional;
8. publicar, se aprovado, somente como explicação contextualizada.

## Linguagem pública

Preferir:

> “A regra X sinalizou que este registro difere da população Y nas condições Z.
> O sinal não demonstra irregularidade.”

Evitar “suspeito”, “fraude”, “desvio”, “superfaturamento” ou “corrupção” sem
decisão competente e contexto jurídico devidamente citado.

## Métricas

- precisão da regra em amostra revisada;
- taxa de falso positivo;
- achados causados por erro de fonte/parser;
- cobertura elegível e excluída;
- tempo de triagem;
- distribuição por órgão sem exposição seletiva;
- estabilidade entre versões.

## Primeiras regras permitidas

Começar por anomalias operacionais de baixo risco:

- lacuna inesperada de datas/edições;
- mudança de schema da fonte;
- documento com hash diferente na mesma identidade;
- total informado divergente da soma determinística dos componentes, com
  tolerância explicitada;
- vínculo normalizado sem evidência.

Regras sobre pessoas, preços ou legalidade só entram após estabilização,
amostra anotada e revisão metodológica.
