# Farmácia Popular: leitura privada e caminho de publicação

## Contrato implementado

`inspect_pharmacy_capture` aceita uma página completa, até 25 registros,
de Outros Pagamentos (tipo 3), no recorte Barreiras/BA. Confere URL solicitada
e final, ano, beneficiário consultado, SHA-256, tamanho, HTTP e paginação.
Parâmetros duplicados, páginas parciais e mistura de modalidades são recusados.
Metadados devem vir do transporte confiável: hash não autentica o emissor.

Somente FARMACIA POPULAR na esfera PRIVADA é interpretada. Outros programas,
inclusive demandas judiciais, não produzem registros nem valores na saída.
Os campos permitidos incluem chave documental privada, data, posição/hash
da evidência e valores documentais. Nomes, identificadores do beneficiário,
contas, agência, processos e texto de rejeição não são devolvidos.

Valores são conferidos com Decimal contra os totais declarados. Repetição
documental, anulação, rejeição ou divergência requerem revisão. Nenhuma linha
repetida é apagada. Competência não é convertida em data de pagamento.
O leitor não cobre múltiplas páginas: precisa de adaptador específico antes
de ampliar esse limite; falha nunca equivale a zero financeiro.

## Bloqueios de publicação

1. O identificador enviado ao FNS é opaco. Quantidade de dígitos ou nome com
   aparência empresarial não comprovam identidade institucional. Conferir
   cadastro oficial do estabelecimento e evidência antes da publicação.
2. O reconciliador atual `fns_cgu_reconciliation` compara emendas do Fundo
   Municipal de Saúde. Seu CNPJ fixo e arquivo anual de emendas não podem ser
   reutilizados para estabelecimentos privados. Ausência naquele arquivo não
   significa ausência do pagamento nem prova que um registro é novo.
3. Verificar a ordem e a identidade documental da fonte antes de deduplicar
   entre bases. Não deduplicar apenas por valor, competência ou nome.

`publication_allowed=false`, `identity_verification=pending` e
`reconciliation=pending` são fixos. Este leitor não escreve no banco nem cria
lançamento financeiro, autorização editorial ou cobertura anual.

## Entrega pública posterior

Seção Saúde dentro de Recursos, separando administração municipal de pagamentos
a estabelecimentos locais. Programa, período, beneficiário institucional,
valor, estágio informado e evidência devem estar explícitos. Não somar esses
pagamentos às receitas municipais ou ao ranking de emendas. Listas paginadas
no servidor; evidências completas somente no detalhe, sem conteúdo bancário.

Próxima entrega: adaptador de identidade institucional e reconciliação
documental, com testes de conflitos e dupla contagem. Só depois habilitar a
projeção pública. O leitor privado não publica dados reais; a apresentação
preparatória está descrita abaixo.

## Apresentação preparada

A rota `/recursos/saude`, acessível de Recursos, possui um estado explícito de
publicação em preparação e links oficiais. Não exibe amostras nem converte
pendência em zero. `readPharmacyPublication` faz validações defensivas de uma
futura projeção revisada, com lista de campos permitidos e limite de 25 linhas.
Não é mecanismo de autorização: a aprovação e atualidade precisam ser
estabelecidas pelo servidor/banco, nunca por parâmetros enviados pelo usuário.

O estado real permanece `pending`, definido no servidor. O componente de
registros está preparado, mas sem alimentação de dados reais. Antes de ativar:
implementar projeção pública auditável, paginação e filtros no servidor,
evidências consultáveis por registro e conferência visual do estado preenchido.
Não há acesso a Storage, dados bancários ou identificadores internos pela rota.
