# ADR 0086 — Empenhos individuais do WebRun e ligação a contratos

## Status

Aceita em 23/09/2026. A preservação é implementada junto com este ADR; a
ligação a contratos é a regra que a próxima etapa deve seguir.

## Contexto

O gate 4 exige seguir um contrato até seus empenhos, liquidações e pagamentos
por chave oficial. A API de dados abertos do portal não expõe esses estágios,
e o TCM-BA entrega PDFs. A única fonte individual observada é o sistema
Sudoeste/WebRun por trás do portal
([`sources/PREFEITURA_DESPESAS_WEBRUN.md`](../sources/PREFEITURA_DESPESAS_WEBRUN.md)).

O empenho não tem campo de contrato. O histórico, texto escrito pela própria
Prefeitura, cita o contrato em parte dos empenhos ("Contrato nº 070-FMS/2025").
A numeração municipal distingue órgãos pelo sufixo: `070/2025` e
`070-FMS/2025` são contratos diferentes. A fonte também repete linhas inteiras,
mistura retenções extra-orçamentárias (`E-`) com empenhos (`O-`) e só tem parte
dos meses anteriores a 2024, porque a série histórica falha no próprio servidor.

## Decisão

### Preservação

- Cada mês fechado é uma partição `month:AAAA-MM`. A grade devolvida pela fonte
  é gravada intacta como `raw_artifact` (SHA-256, relida e conferida) no
  corredor privado `municipal-transparency/despesas-webrun/`.
- Cada chave oficial distinta (`CHAVE`, `O-<n>` ou `E-<n>`) gera um
  `raw_record` do tipo `municipal_commitment_webrun`, com a linha literal da
  fonte como payload. Repetições idênticas ficam no bruto e são contadas nas
  métricas; a mesma chave com conteúdo diferente invalida o mês inteiro.
- A partição só termina `complete` quando o total declarado pela regra, o fim
  de página e as linhas coincidem e toda linha passa no contrato (chave,
  número, valor decimal, data no mês). Meses anteriores a 2024 terminam
  `partial`, com a indisponibilidade da série histórica registrada como falha
  parcial não recuperável; nunca `complete` nem vazios.
- Recoletar um mês com o mesmo SHA-256 é idempotente. Um SHA-256 diferente cria
  novo artefato e novas versões dos registros; nada é sobrescrito.

### Ligação empenho → contrato

A ligação é determinística, versionada (`commitment-contract-link/1.0.0`) e só
existe quando todas as condições valem:

1. o empenho é orçamentário (`O-`);
2. o histórico contém uma citação literal reconhecida pelo padrão versionado
   `contrato nº <número>`, e o trecho citado é guardado junto da ligação;
3. o número citado, normalizado sem apagar sufixo de órgão nem ano, é igual a
   exatamente um `contratoNumero` dos contratos municipais preservados;
4. o favorecido do empenho corresponde ao contratado pelo nome normalizado.

Citação sem contrato correspondente, com mais de um candidato ou com favorecido
divergente fica como `citacao_sem_confirmacao`, visível apenas na revisão
humana. Valor parecido, data próxima, nome aproximado ou leitura por LLM nunca
criam ligação.

### Estágios

Empenho, liquidação e pagamento continuam entidades separadas. Nenhum total
soma estágios diferentes, e registros `E-` nunca entram em série de empenho.
Publicar qualquer valor exige normalização com versão de metodologia própria,
fora deste ADR.

## Alternativas rejeitadas

- **Exportação da grade pelo botão "Exportar Dados":** formato não observado e
  download não autorizado na sondagem; pode substituir a grade quando se
  mostrar estável, mantendo a mesma chave.
- **Automação de navegador:** mais frágil e cara que as três requisições HTTP
  observadas, sem ganho de evidência.
- **Ligar por favorecido e valor:** sem chave oficial; produziria falsos
  vínculos entre contratos do mesmo fornecedor.
- **Extrair o número do contrato com LLM:** LLMs não decidem vínculos; o padrão
  literal é auditável e reproduzível.

## Consequências

- o acervo cresce ~20–45 MB por mês preservado (a maior parte é JavaScript de
  interface repetido por linha), abaixo do limite de 100 MB por objeto do
  bucket;
- mudança de formulário na fonte (IDs de campo, regra, paginação) falha o mês
  explicitamente em vez de gravar dados parciais;
- o rastro individual antes de 2024 fica incompleto até a fonte corrigir a
  série histórica ou outra fonte oficial cobrir o período;
- liquidações (formulário 7907) e pagamentos (7910) exigem sonda própria antes
  de seguir o mesmo modelo.
