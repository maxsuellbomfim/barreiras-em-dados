# Operação do catálogo mensal do TCM-BA

## Escopo e limite

O comando cataloga as prestações mensais e os documentos entregues pela
Prefeitura de Barreiras no e-TCM. Ele preserva cada resposta HTML e só fecha a
competência quando a contagem integral confere. Esta etapa não baixa os PDFs,
não extrai valores e não cria projeção pública financeira.

## Restrição de rede observada

Em 24/08/2026, o endpoint oficial respondeu pelo acesso residencial usado na
validação, mas expirou quatro vezes antes da página inicial a partir de um
runner hospedado pelo GitHub. A execução `32750879301` foi registrada como
falha; a competência não recebeu cobertura `complete`.

Não trate esse evento como competência vazia. Enquanto o TCM-BA não responder
de forma estável a datacenters, use o executor local pelo IP autorizado. Não
adicione proxy informal, serviço de bypass ou espelho não oficial.

## Execução local segura

O arquivo ignorado `.env.collector.local` deve conter somente:

```dotenv
COLLECTOR_POOLER_HOST=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_WORKLOAD_EMAIL=
```

Execute na raiz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/rotate-local-collector-credentials.ps1

powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-monthly-catalog.ps1
```

O primeiro comando rotaciona exclusivamente a role PostgreSQL compartilhada
pelos coletores e o usuário técnico municipal autorizado. Ele atualiza os dois
secrets correspondentes no GitHub e cria o arquivo ignorado
`.collector-credentials.local.json`. Os valores são cifrados pela DPAPI no
escopo `CurrentUser`: somente o mesmo usuário do Windows nesta máquina pode
descriptografá-los. Nenhuma senha é escrita em texto simples, passada em
argumento de processo, exibida no terminal ou registrada no Git.

O piloto exige exatamente abril de 2023 e 1.824 documentos. O segundo comando
carrega o cofre DPAPI automaticamente. Se ainda não houver cofre, mantém a
alternativa de solicitar as senhas com entrada oculta. Em ambos os casos, as
variáveis de ambiente são removidas no bloco `finally`. O replay local usa até
120 requisições por minuto para concluir a paginação antes de a sessão JSF do
e-TCM expirar; o parâmetro é validado e nunca pode ultrapassar esse teto.

Para outra competência, desative a contagem específica:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-monthly-catalog.ps1 `
  -MonthFrom 2023-05 -MonthTo 2023-05 -ExpectedDocuments 0
```

Antes de ampliar o intervalo, confirme no Supabase a partição, o número de
documentos, os hashes e o replay idempotente. Backfill grande deve continuar em
lotes mensais; uma falha não autoriza marcar os meses seguintes como vazios.

## Piloto comprovado

Em 24/08/2026, o replay local de `2023-04` terminou com o evento
`collector_tcm_ba_month_completed`: 1.824 documentos, 193 interações brutas e
1.825 registros normalizados. A consulta independente ao banco confirmou a
partição `competence:2023-04` como `complete`, execução `succeeded` e 1.824
registros observados.

As respostas AJAX do JSF chegam como `text/xml`. Para respeitar a lista de MIME
types do bucket privado, o persistidor registra o equivalente
`application/xml` no artefato e mantém o `Content-Type` literal da origem nos
headers preservados. Os bytes e o SHA-256 não são alterados.
