param(
    [ValidateRange(1,200)][int]$ActsLimit=20,
    [ValidateRange(1,1000)][int]$Pages=800,
    [ValidateRange(1,8)][int]$Workers=4,
    [ValidateRange(0,3600)][int]$ActsMaxSeconds=0,
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath='',
    [string]$TesseractDir='C:\Program Files\Tesseract-OCR',
    [ValidateRange(0,900)][int]$SourceLockTimeoutSeconds=60,
    [switch]$Scheduled
)
# Dreno local do OCR do Diário: os mesmos quatro passos de
# .github/workflows/ocr-gazette-backlog.yml (texto embutido e candidatos,
# OCR das páginas sem texto útil, reorganização das edições, candidatos
# após OCR). O cron do GitHub dispara ~5 vezes por dia; as 634 edições do
# backfill 2021-2022 (~30 mil páginas escaneadas) levariam semanas lá.
# O modelo tessdata_best fixado fica em data/tessdata_best/por.traineddata
# (sha256 conferido pelo motor); páginas OCR são idempotentes por artefato,
# página e versão do extrator, então rodar junto com o GitHub não duplica.
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$names=@('DATABASE_URL','APP_ENV','LOG_LEVEL','PYTHONDONTWRITEBYTECODE','PYTHONPATH','PERSISTENCE_MODE','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','SUPABASE_WORKLOAD_EMAIL','SUPABASE_WORKLOAD_PASSWORD','SUPABASE_RAW_ARTIFACTS_BUCKET','GAZETTE_TESSDATA_DIR','OMP_THREAD_LIMIT','PATH')
$previous=@{}
foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$certificate=$null; $runLock=$null; $resultCode=1; $stage='initialization'
try {
    $CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
    $stateRoot=Join-Path $CredentialRoot 'data/gazette-ocr'
    [IO.Directory]::CreateDirectory($stateRoot) | Out-Null
    $model=Join-Path $CredentialRoot 'data/tessdata_best/por.traineddata'
    if(-not (Test-Path -LiteralPath $model)){throw 'Tesseract model unavailable'}
    if(-not (Test-Path -LiteralPath (Join-Path $TesseractDir 'tesseract.exe'))){throw 'Tesseract unavailable'}
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
    $env:PYTHONPATH=(Join-Path $projectRoot 'workers/collectors/src')+';'+(Join-Path $projectRoot 'workers/document-processing/src')
    $env:PERSISTENCE_MODE='postgres-supabase'
    $env:SUPABASE_URL='https://mpladsyzilmgiefejpkq.supabase.co'
    $env:SUPABASE_PUBLISHABLE_KEY=$config.SUPABASE_PUBLISHABLE_KEY
    $env:SUPABASE_WORKLOAD_EMAIL=$config.SUPABASE_WORKLOAD_EMAIL
    $env:SUPABASE_WORKLOAD_PASSWORD=$credentials.WorkloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET='raw-artifacts'
    $env:GAZETTE_TESSDATA_DIR=Split-Path -Parent $model
    # Um Tesseract de uma thread por página paralela, como no workflow.
    $env:OMP_THREAD_LIMIT='1'
    $env:PATH="$TesseractDir;$env:PATH"
    $stage='collector'
    # Mesma sequência do workflow; sem redirecionar stderr (PowerShell 5.1
    # transforma em ErrorRecord). O registro fica em raw.extraction_jobs.
    $steps=@(
        @('barreiras_docproc.commands.process_gazette_acts','--limit',"$ActsLimit",'--max-seconds',"$ActsMaxSeconds"),
        @('barreiras_docproc.commands.ocr_gazette_pages','--limit-pages',"$Pages",'--workers',"$Workers"),
        @('barreiras_docproc.commands.segment_gazette_editions','--limit','50'),
        @('barreiras_docproc.commands.process_gazette_acts','--limit','20')
    )
    $resultCode=0
    foreach($step in $steps){
        & $PythonPath -X utf8 -B -m $step
        if($LASTEXITCODE -ne 0){$resultCode=$LASTEXITCODE; break}
    }
} catch {
    $resultCode=1
    if($stage -eq 'source_lock' -and $_.Exception -is [TimeoutException]){$resultCode=75}
    Write-Output (@{event='gazette_ocr_helper';status='failed';stage=$stage;line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json -Compress)
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
