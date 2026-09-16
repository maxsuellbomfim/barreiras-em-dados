# ADR 0032 — Normalização determinística de contratos PNCP

## Contexto

O coletor PNCP já preservava respostas brutas de contratações e contratos, mas
as tabelas normalizadas procurement.procurements,
procurement.suppliers e procurement.contracts permaneciam vazias. As
projeções de execução, portanto, não conseguiam mostrar os contratos oficiais
nem a evidência correspondente.

## Decisão

Criar a função interna procurement.normalize_pncp_contracts(integer), executada
pelo worker técnico após cada coleta:

- usa somente raw.raw_records com record_type pncp_contratacao e pncp_contrato;
- identifica Barreiras pelo IBGE 2903201 e pelo CNPJ oficial informado no
  próprio registro;
- usa numeroControlePNCP como chave externa da contratação/contrato;
- liga contratos à contratação por
  numeroControlePncpCompra/numeroControlePNCPCompra;
- identifica pessoa jurídica por CNPJ; nome sozinho nunca cria identidade de
  fornecedor;
- mantém origin_raw_record_id, version e supersedes_id;
- compara o hash do registro bruto antes de criar uma nova versão;
- expõe apenas métricas de execução ao worker por uma função security definer;
- não cria empenhos a partir de numeroContratoEmpenho, pois esse campo não é,
  por si só, prova de uma inscrição contábil.

A função não é concedida a anon ou authenticated e não é uma superfície
PostgREST. A leitura pública continua sendo feita pelas funções api.*.

## Consequências

Contratos e fornecedores podem aparecer no explorador público com valores
oficiais, origem bruta e vínculo à contratação. Alterações futuras do PNCP
geram versões novas, sem apagar a versão anterior. O resumo de execução passa a
distinguir corretamente contrato existente de empenho, liquidação e pagamento
ainda não normalizados.

A próxima etapa é adicionar os endpoints oficiais de empenhos/execução
financeira e ligá-los somente por identificadores verificáveis.

## Correção aditiva — 15/09/2026

O replay `34988436563` revelou regressão de versões: seis novos registros
oficiais geraram doze versões normalizadas; a última versão de cada contrato
apontava novamente ao snapshot anterior. A rotina percorria todos os registros
do mais novo para o mais antigo e comparava cada um somente com a versão
normalizada corrente. Por isso, contagens de inserções não comprovavam atualização.

A rotina deve selecionar apenas o snapshot mais recente por chave oficial
(`numeroControlePNCP`, com a grafia alternativa já aceita), usando ordem
determinística de coleta, criação e identificador. A deduplicação acontece antes
do limite; registros já representados pelo hash corrente não consomem o lote.
Histórico e `supersedes_id` são preservados. Corrigir o ponteiro exige uma nova
versão auditável, nunca apagar versões antigas nem reescrever migrations aplicadas.

O teste de aceite executa a função real: novo seguido de antigo não regride;
repetição não cria versões; nova evidência cria uma única versão; múltiplas
chaves, limite, grafia alternativa, empate e escopo territorial são verificados.
Esta correção não resolve a paginação mutável da fila de coleta nem transforma
resposta 404 em inexistência oficial de contratos.

## Órgãos distintos — 16/09/2026

O IBGE identifica território, não o contratante. A normalização exige cadastro
único do CNPJ em `org.public_bodies` e controle PNCP compatível. O código legado
exato `PREF-BARREIRAS` é mapeado apenas ao CNPJ da Prefeitura, sem fallback para
qualquer órgão executivo. Cadastro ausente ou ambíguo não autoriza atribuição.

A contratação-pai é resolvida pela chave oficial e por seu próprio órgão, que
pode ser diferente do contratante. Duas grafias conflitantes do campo de vínculo
bloqueiam a nova normalização do contrato. Órgão ou vínculo corrigido gera nova
versão mesmo quando o hash bruto não mudou, sem apagar versões anteriores.
Os auxiliares permanecem privados; o worker usa a função normalizadora existente.
Esta migração não importa o par preservado nem cadastra automaticamente fundos.

A auditoria read-only encontrou dois contratos antigos atribuídos a
`PREF-BARREIRAS` apesar de CNPJ distinto na fonte: `50525166000108-2-000062/2026`
(Fundo Municipal de Cultura) e `30667266000153-2-000013/2026` (Fundo Municipal
de Educação). Ambos têm contratação-pai vinculada. A nova regra evita novas
atribuições desse tipo, mas a reparação desses dois registros depende do cadastro
documentado dos fundos e de replay validado; não é efetuada por esta migração.
