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
  -File scripts/run-tcm-ba-monthly-catalog.ps1
```

O piloto exige exatamente abril de 2023 e 1.824 documentos. As senhas do login
PostgreSQL e do usuário técnico do Storage são solicitadas com entrada oculta,
mantidas somente na memória e removidas das variáveis de ambiente no bloco
`finally`. O script nunca grava nem imprime essas credenciais.

Para outra competência, desative a contagem específica:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-monthly-catalog.ps1 `
  -MonthFrom 2023-05 -MonthTo 2023-05 -ExpectedDocuments 0
```

Antes de ampliar o intervalo, confirme no Supabase a partição, o número de
documentos, os hashes e o replay idempotente. Backfill grande deve continuar em
lotes mensais; uma falha não autoriza marcar os meses seguintes como vazios.
