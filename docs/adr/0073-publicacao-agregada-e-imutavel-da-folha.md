# ADR 0073 — Publicação agregada e imutável da folha

- Estado: aceita
- Data: 2026-08-21

## Contexto

O PDF mensal `tipo=1` da relação de servidores possui texto embutido, linhas
individuais e totalizadores por unidade. A amostra de julho de 2026 contém 133
subtotais que, somados por código determinístico, fecham exatamente com o total
geral do documento. As linhas individuais, porém, incluem campos sem
necessidade para responder às perguntas populares iniciais sobre tamanho e
custo mensal da folha.

Publicar a tabela inteira aumentaria o risco de exposição de dados pessoais e
descontos individuais. Publicar somente o total geral sem validar os subtotais
permitiria que um erro de extração parecesse um fato oficial.

## Decisão

O primeiro produto público de folha será exclusivamente mensal e agregado. A
tabela append-only `hr.payroll_report_aggregates` guarda:

- competência e órgão público;
- quantidade total de vínculos reportados;
- proventos, descontos e líquido totais em `numeric(20,2)`;
- quantidade de subtotais reconciliados;
- versão do parser, instante de validação e versão/supersessão;
- relações obrigatórias com o registro de catálogo e o PDF bruto preservado.

O banco aceita a linha somente quando:

1. o registro bruto é do recurso oficial `servidores` e `tipo=1`;
2. competência, URL e chave do registro coincidem com o artefato documental;
3. `proventos - descontos = líquido` de forma exata;
4. o parser e o totalizador já reconciliaram todos os subtotais com o total
   geral do PDF.

A tabela interna tem RLS forçada, não concede leitura ao frontend e rejeita
`UPDATE` e `DELETE`. Correções criam nova versão. A função pública
`api.get_public_payroll_months` retorna apenas os totais vigentes, fonte, hash,
data de coleta e versão do parser.

## Fora de escopo

- nomes, CPF, matrícula, conta bancária ou qualquer linha individual;
- descontos pessoais ou componentes remuneratórios por pessoa;
- estagiários (`tipo=3`) e terceirizados (`tipo=4`), cujos leiautes e conceitos
  são diferentes;
- classificação entre efetivos e comissionados sem regra documental própria;
- interpretação por IA dos valores ou qualquer juízo de irregularidade.

## Consequências

- a população poderá conhecer o custo e o tamanho mensal da folha com fonte
  verificável, sem expor linhas pessoais;
- um PDF truncado ou cujo total não fecha falha de forma explícita e não entra
  na projeção;
- retificações preservam a versão anterior e seu hash;
- a publicação inicial não responde ainda quanto é pago por tipo de vínculo,
  secretaria ou cargo.
