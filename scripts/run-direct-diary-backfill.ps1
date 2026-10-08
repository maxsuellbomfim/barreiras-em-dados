param(
    [ValidateRange(1,1000000)][int]$FirstEdition=3353,
    [ValidateRange(1,1000000)][int]$LastEdition=3988,
    [ValidatePattern('^\d{4}(,\d{4})*$')][string]$Years='2021,2022,2023',
    [ValidateRange(1,50)][int]$Limit=15,
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath='',
    [ValidateRange(0,900)][int]$SourceLockTimeoutSeconds=60,
    [switch]$Scheduled
)
# Backfill das edições antigas do Diário (3353-3988) pelo executor local:
# o cron do GitHub pula a maioria das janelas horárias. Mesmo cofre e mesma
# identidade técnica dos outros coletores locais; a partição
# backfill:<a>-<b> no banco guarda o que já foi sondado, então execuções
# locais e do GitHub podem se alternar sem repetir trabalho.
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$names=@('DATABASE_URL','APP_ENV','LOG_LEVEL','PYTHONDONTWRITEBYTECODE','PYTHONPATH','PERSISTENCE_MODE','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','SUPABASE_WORKLOAD_EMAIL','SUPABASE_WORKLOAD_PASSWORD','SUPABASE_RAW_ARTIFACTS_BUCKET','QUERIDO_DIARIO_MAX_DOCUMENT_BYTES','HTTP_READ_TIMEOUT_SECONDS','HTTP_MAX_ATTEMPTS')
$previous=@{}
foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$certificate=$null; $runLock=$null; $resultCode=1; $stage='initialization'
try {
    $CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
    $stateRoot=Join-Path $CredentialRoot 'data/direct-diary-backfill'
    [IO.Directory]::CreateDirectory($stateRoot) | Out-Null
    $stage='source_lock'
    . (Join-Path $PSScriptRoot 'lib/collector-source-lock.ps1')
    $runLock=Wait-CollectorSourceLock -Path (Join-Path $stateRoot 'source.lock') -TimeoutSeconds $SourceLockTimeoutSeconds
    if($null -eq $runLock){throw [TimeoutException]::new('Source lock timed out')}
    $stage='credentials'
    . (Join-Path $PSScriptRoot 'lib/collector-credential-store.ps1')
    $config=ConvertFrom-StringData ((Get-Content -LiteralPath (Join-Path $CredentialRoot '.env.collector.local') -Encoding UTF8 | Where-Object {$_.Trim() -and -not $_.TrimStart().StartsWith('#')}) -join "`n")
    $credentials=Read-CollectorCredentialStore -Path (Join-Path $CredentialRoot '.collector-credentials.local.json') -ExpectedProjectRef 'mpladsyzilmgiefejpkq'
    if($null -eq $credentials){throw 'Protected credentials unavailable'}
    if(-not $PythonPath){$PythonPath=Join-Path $env:LOCALAPPDATA 'Python/pythoncore-3.14-64/python.exe'}
    if(-not (Test-Path -LiteralPath $PythonPath)){throw 'Python unavailable'}
    $certificate=New-TemporaryFile
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config/certificates/supabase-prod-ca-2021.crt') -Destination $certificate.FullName
    $password=[Uri]::EscapeDataString($credentials.DatabasePassword)
    $ca=[Uri]::EscapeDataString($certificate.FullName)
    $env:DATABASE_URL="postgresql://collector_querido_diario.mpladsyzilmgiefejpkq:${password}@$($config.COLLECTOR_POOLER_HOST):5432/postgres?sslmode=verify-full&sslrootcert=${ca}"
    $env:APP_ENV='development'; $env:LOG_LEVEL='INFO'; $env:PYTHONDONTWRITEBYTECODE='1'
    $env:PYTHONPATH=Join-Path $projectRoot 'workers/collectors/src'
    $env:PERSISTENCE_MODE='postgres-supabase'
    $env:SUPABASE_URL='https://mpladsyzilmgiefejpkq.supabase.co'
    $env:SUPABASE_PUBLISHABLE_KEY=$config.SUPABASE_PUBLISHABLE_KEY
    $env:SUPABASE_WORKLOAD_EMAIL=$config.SUPABASE_WORKLOAD_EMAIL
    $env:SUPABASE_WORKLOAD_PASSWORD=$credentials.WorkloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET='raw-artifacts'
    # Edições escaneadas chegam a dezenas de MB; mesmos limites do workflow.
    $env:QUERIDO_DIARIO_MAX_DOCUMENT_BYTES='268435456'
    $env:HTTP_READ_TIMEOUT_SECONDS='60'
    $env:HTTP_MAX_ATTEMPTS='5'
    $stage='collector'
    # Sem redirecionar stderr: no PowerShell 5.1 isso vira ErrorRecord e, com
    # ErrorActionPreference=Stop, derruba a execução. O registro fica em
    # source.collection_runs / collection_partitions (partição backfill:a-b).
    & $PythonPath -X utf8 -B -m barreiras_collectors.commands.collect_direct_diary_backfill --first-edition $FirstEdition --last-edition $LastEdition --years $Years --limit $Limit
    $resultCode=$LASTEXITCODE
} catch {
    $resultCode=1
    if($stage -eq 'source_lock' -and $_.Exception -is [TimeoutException]){$resultCode=75}
    # Só campos seguros saem do wrapper (sem URL, sem segredo).
    Write-Output (@{event='direct_diary_backfill_helper';status='failed';stage=$stage;line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json -Compress)
} finally {
    try {
        foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
        if($null -ne $certificate){Remove-Item -LiteralPath $certificate.FullName -Force}
    } finally {
        if($null -ne $runLock){$runLock.Dispose()}
        $credentials=$null; $config=$null; $password=$null
    }
}
exit $resultCode
