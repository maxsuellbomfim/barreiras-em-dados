# ADR 0097 — Verificações de alerta sobre pagamentos e compras

## Status

Aceita em 09/10/2026. O titular pediu regras que apontem onde olhar
("quando vamos descobrir as corrupções?") e autorizou a execução ("faça
tudo").

## Contexto

A plataforma não declara crime nem irregularidade (ADR 0005, ADR 0018): ela
mostra fatos oficiais que pedem explicação. Quatro verificações foram
propostas, cruzando bases já preservadas:

1. pagamento a fornecedor com sanção vigente na data do pagamento;
2. empresa aberta pouco antes de receber contrato relevante;
3. compra direta fracionada (várias dispensas que, somadas, passariam do
   limite que obrigaria licitação);
4. licitação com um único concorrente.

Antes de publicar qualquer lista, cada verificação foi medida em produção.

## Decisão

### 1. Sanção vigente na data do pagamento

O alcance legal da sanção decide se ela proíbe Barreiras de contratar:

| Sanção | Alcance |
| --- | --- |
| Declaração de inidoneidade | toda a administração pública |
| Impedimento de licitar e contratar (Lei 14.133, art. 156, III) | só o ente federativo que aplicou (art. 156, § 4º) |
| Suspensão temporária (Lei 8.666, art. 87, III) | o órgão que aplicou (entendimento do TCU) |
| Proibição judicial de contratar com o poder público | definido na decisão |
| Multa, publicação extraordinária (CNEP), acordo de leniência | não proíbe contratar |
| CEPIM | convênios e transferências da União |

Medição em 09/10/2026 (pagamentos da Prefeitura de 2024 a 2026, favorecido
ligado ao CNPJ pelo cadastro da Receita, ADR 0093–0095): **nenhum pagamento
a fornecedor com sanção válida para Barreiras**. A única inidoneidade da base
não teve pagamento no período. Houve 13 pagamentos (cerca de R$ 7,6 mil) a
5 empresas impedidas ou suspensas por outros órgãos (prefeituras de outros
estados, universidade federal, consórcio), sanções que não alcançam
Barreiras.

Publicar uma lista "pagamentos a empresas sancionadas" com esses casos
induziria o leitor a erro. Decisão: não publicar essa lista; o cartão de
sanção que o site já mostra (`/licitacoes` e página do fornecedor) passa a
dizer o alcance legal de cada sanção (`supplier-sanction-scope/1.0.0`,
`sanctionLegalScope` em `apps/web/lib/supplier-sanctions.mjs`), com
classificação conservadora e "não classificado" quando o tipo não é
reconhecido.

Limite: só os favorecidos com CNPJ identificado pelo cadastro (314 em
09/10/2026) e só as sanções consultadas para fornecedores publicados.

### 3. Compra fracionada

O critério da lei (Lei 14.133, art. 75, § 1º) é a soma, no exercício, das
contratações diretas de objetos de mesma natureza pela mesma unidade gestora,
não a soma por fornecedor. O PNCP traz 38 dispensas da Prefeitura de 2024 a
2026. O único caso com soma por fornecedor acima do limite (2 dispensas de
2025 de manutenção da rede de telefonia, R$ 87.030 somadas) era a mesma
contratação publicada duas vezes: mesmo objeto, mesmos três itens e valores,
e só uma virou contrato (R$ 43.515). **Nenhum fracionamento identificado.**
Somar publicações sem conferir contratos teria criado um alerta falso.

Limite: só as dispensas publicadas no PNCP; empenhos da Prefeitura não
informam modalidade.

### 4. Licitação com único concorrente

O PNCP não informa quantos concorrentes participaram (resultados trazem só o
vencedor de cada item). A verificação depende das atas de sessão da
plataforma de pregão, que é fonte nova a pesquisar. **Não executada.**

### 2. Empresa recém-aberta

O extrato do cadastro da Receita (ADR 0093) não guarda a data de início de
atividade. A verificação depende de ampliar esse extrato com o campo, dado
público da própria Receita, sem dado pessoal. **Pendente da próxima coleta.**

## Consequências

- Nenhuma lista de "alerta" vai ao ar sem medição, conferência dos casos e
  registro de revisão, como no ADR 0096.
- Resultados zero também são resultado: ficam registrados aqui com data,
  regra e limite de cobertura.
- Novas verificações seguem o mesmo roteiro: regra determinística e
  versionada, medição em produção, conferência dos candidatos contra o
  documento oficial e só então publicação.
