# Operação do coletor do Querido Diário

## Escopo

Este runbook cobre somente a aquisição diária dos metadados de edições do
Querido Diário para o território IBGE `2903201` (Barreiras). O job preserva a
resposta bruta no bucket privado e registra a coleta no PostgreSQL. Ele não
extrai atos, não normaliza pessoas e não publica conteúdo.

Workflow: `.github/workflows/collect-querido-diario.yml`.

## Agendamento

- execução automática: todos os dias às `11:17 UTC`, atualmente `08:17` em
  Barreiras;
- janela automática: o dia anterior, resolvido com `America/Sao_Paulo`;
- backfill manual: no máximo sete dias corridos, incluindo as duas pontas;
- concorrência: uma execução por vez, sem cancelar a anterior;
- timeout: 20 minutos.

O cron do GitHub usa UTC. Se a legislação brasileira voltar a adotar horário de
verão, o horário local de início poderá mudar, mas a data de coleta continuará
sendo resolvida no fuso de Barreiras.

## Segredos e privilégios

O job lê do cofre de Actions:

- `QUERIDO_DIARIO_DATABASE_URL`;
- `QUERIDO_DIARIO_SUPABASE_WORKLOAD_EMAIL`;
- `QUERIDO_DIARIO_SUPABASE_WORKLOAD_PASSWORD`.

Configurações públicas ficam em variáveis do repositório:

- `QUERIDO_DIARIO_SUPABASE_URL`;
- `QUERIDO_DIARIO_SUPABASE_PUBLISHABLE_KEY`.

Esses valores não pertencem à Vercel. O login PostgreSQL é
`collector_querido_diario`, exige TLS `verify-full` com a CA oficial versionada
e não possui `UPDATE` ou `DELETE` no bruto. O Storage usa chave publicável e
uma identidade Auth técnica limitada por UUID e prefixo. Chaves
`service_role`/secret são recusadas pelo próprio coletor.

Builds de pull requests não recebem esses segredos. O workflow de produção tem
apenas `contents: read`, e todas as Actions externas estão fixadas por SHA.

## Execução manual

Pelo GitHub:

1. abra **Actions → Coletar Querido Diário → Run workflow**;
2. deixe as datas vazias para coletar ontem; ou
3. preencha `since` e `until` em `YYYY-MM-DD`.

Com GitHub CLI:

```powershell
gh workflow run collect-querido-diario.yml `
  --repo maxsuellbomfim/barreiras-em-dados `
  -f since=2026-06-10 `
  -f until=2026-06-10
```

Repetir a mesma janela é esperado: o resultado deve informar registros
existentes, sem criar duplicatas ou sobrescrever o objeto bruto.

## Falhas e replay

Depois que o checkout está disponível, uma falha posterior gera
`artifacts/collector-failure.json` sem stack trace, URL de banco, senha ou
token. O arquivo é enviado como artifact de Actions por 30 dias e contém apenas
contexto operacional: fonte, território, janela quando resolvida, commit e URL
da execução. Falhas anteriores ou no próprio checkout aparecem somente nos logs
do workflow, pois o código que cria a DLQ ainda não está disponível.

Procedimento:

1. classificar a falha como fonte, autenticação, rede, contrato ou código;
2. não interpretar falha como “zero edições”;
3. corrigir a causa sem editar registros brutos existentes;
4. repetir a mesma janela por execução manual;
5. confirmar idempotência pelos contadores e hashes;
6. registrar rotação de credencial caso a causa envolva segredo.

O artifact de falha é uma DLQ operacional temporária. Os artefatos públicos
brutos bem-sucedidos seguem a política de retenção e versionamento de
`docs/DATA_GOVERNANCE.md`; não são apagados ao expirar a DLQ.

## Verificações antes de alterar o workflow

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='workers/collectors/src'
python -B -m unittest discover -s tests/collectors -p 'test_*.py' -v
python -m ruff check workers/collectors/src tests/collectors
```

Também devem ser confirmados:

- YAML válido;
- hash da CA oficial;
- ausência de segredos no diff;
- janela automática e backfill;
- falha sanitizada;
- replay real sem duplicação.

## Limitações atuais

- a rotina preserva páginas JSON de metadados, ainda não PDFs/TXT;
- o estado da coleta ainda não é uma projeção pública no portal;
- alertas externos ainda dependem da observação do GitHub Actions;
- backup e restauração completa do Storage ainda precisam de exercício
  documentado.
