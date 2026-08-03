# ADR 0033 — Detalhes públicos de contratos PNCP

## Contexto

A normalização do PR 132 já criou contratos e fornecedores rastreáveis, mas a
página pública mostrava somente contagens e o valor agregado. O cidadão não
conseguia responder, dentro da própria contratação, quem contratou, qual o
número do contrato, o valor atual e a vigência.

## Decisão

A função-base de execução do PNCP passa a retornar uma lista pública de
contratos atuais, contendo apenas campos necessários para compreensão:

- identificador e número do contrato;
- nome e CNPJ público do fornecedor;
- valor inicial e valor atual;
- assinatura e vigência;
- URL da resposta oficial preservada e data de coleta.

O wrapper de evidências permanece ativo, acrescentando metadados de documentos
filhos sem tornar o Storage público. A interface mostra os detalhes em uma
sanfona dentro de “Execução financeira ligada” e explica que valor contratado
não é empenho nem pagamento.

## Consequências

A contratação do PNCP fica legível sem recalcular valores nem misturar estágios
contábeis. Empenhos, liquidações e pagamentos continuam aparecendo em campos
separados e somente quando houver vínculo oficial. Registros antigos da API
sem a chave contracts continuam válidos no cliente, sendo interpretados como
lista vazia.

A próxima etapa é ligar, por identificador oficial, a fonte de empenhos e
pagamentos municipais.
