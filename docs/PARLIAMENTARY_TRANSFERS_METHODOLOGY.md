# Emendas e recursos destinados a Barreiras

## Pergunta pública

Quem destinou recursos a Barreiras, quanto foi destinado e quanto alcançou um
estágio financeiro confirmado pela fonte oficial?

## Métricas

- **valor destinado**: valor associado à emenda na distribuição de recursos;
- **valor empenhado**: valor dos empenhos ligados à parceria da proposta;
- **valor pago confirmado**: ordens de pagamento com situação `Paga`;
- **quantidade de emendas**: distribuições oficiais distintas após deduplicar
  reexecuções do coletor;
- **emendas integralmente pagas**: quantidade em que o pago confirmado é igual
  ou superior ao valor destinado.

Os cálculos usam `numeric(20,2)` no PostgreSQL. IA não soma valores, não ordena
o ranking e não decide autoria.

## Autoria

O tipo publicado no campo oficial da emenda define a seção:

- `Individual` entra no ranking de pessoas;
- `Comissão`, `Bancada` e autoria coletiva entram em ranking separado;
- autoria ausente ou desconhecida não é transformada em pessoa.

Solicitante, recebedor, beneficiário e autor são papéis diferentes. Uma comissão
não transfere crédito individual aos seus integrantes.

## Ligação com perfis políticos

O nome informado pelo Transferegov não é comparado livremente com nomes de
parlamentares. A ligação pública exige um crosswalk aprovado que registre:

- a grafia oficial observada no Transferegov;
- o identificador do perfil oficial na Câmara ou na ALBA;
- uma candidatura oficial já reconciliada com o TSE;
- URLs e nota de evidência que sustentem a decisão.

Variações de grafia podem apontar para o mesmo perfil, mas cada uma precisa de
evidência própria. Autoria sem crosswalk permanece visível no ranking, sem link
para pessoa. Comissões e bancadas nunca são ligadas a um perfil individual.

## Reconciliação e ausência

Estágios financeiros só são atribuídos ao autor quando a proposta tem uma única
distribuição. Com múltiplas distribuições, o sistema exibe a ambiguidade e não
divide o pagamento por aproximação. Campo ausente significa “não encontrado nos
endpoints consultados”; não significa zero, cancelamento ou inexistência em
outra base.

## Fonte e cobertura inicial

Fonte: API pública Gestão de Parcerias do Transferegov, filtrada pelo código
IBGE `2903201`. A cobertura inicial observada contém três propostas de 2025. O
painel crescerá com a coleta recorrente e com fontes federais e estaduais
complementares, mantendo fonte, data e hash da evidência.
