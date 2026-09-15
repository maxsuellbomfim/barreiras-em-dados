param(
    [ValidateRange(2021,2100)][int]$Year=(Get-Date).Year,
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath='',
    [ValidateRange(0,900)][int]$SourceLockTimeoutSeconds=900,
    [switch]$Scheduled
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$names=@('DATABASE_URL','APP_ENV','LOG_LEVEL','PYTHONDONTWRITEBYTECODE','PYTHONPATH','PERSISTENCE_MODE','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','SUPABASE_WORKLOAD_EMAIL','SUPABASE_WORKLOAD_PASSWORD','SUPABASE_RAW_ARTIFACTS_BUCKET')
$previous=@{}
foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$certificate=$null; $runLock=$null; $resultCode=1
$stateRoot=$null; $stage='initialization'; $startedAt=[DateTime]::UtcNow.ToString('o')
function Write-PharmacyAttempt {
    param([string]$Status,[string]$Reason='',[switch]$Finished)
    if($null -eq $stateRoot){return}
    $attempt=[ordered]@{event='pharmacy_refresh_attempt';year=$Year;status=$Status;stage=$stage;started_at=$startedAt;finished_at=$null}
    if($Finished){$attempt.finished_at=[DateTime]::UtcNow.ToString('o')}
    if($Reason){$attempt.reason=$Reason}
    $path=Join-Path $stateRoot 'attempt.json'
    $temporary=Join-Path $stateRoot ([Guid]::NewGuid().ToString('N')+'.attempt.tmp')
    try {
        [IO.File]::WriteAllText($temporary,($attempt | ConvertTo-Json -Compress))
        Move-Item -LiteralPath $temporary -Destination $path -Force
    } finally {
        if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary}
    }
}
try {
    $CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
    $stateRoot=Join-Path $CredentialRoot "data/pharmacy-refresh/$Year"
    [IO.Directory]::CreateDirectory($stateRoot) | Out-Null
    $stage='source_lock'
    Write-PharmacyAttempt -Status 'waiting'
    . (Join-Path $PSScriptRoot 'lib/collector-source-lock.ps1')
    # Catch-up tasks can start together after the computer wakes. Wait for the
    # same exclusive source lock before loading secrets or creating a batch.
    $runLock=Wait-CollectorSourceLock -Path (Join-Path $CredentialRoot 'data/pharmacy-refresh/source.lock') -TimeoutSeconds $SourceLockTimeoutSeconds
    if($null -eq $runLock){throw [TimeoutException]::new('Source lock timed out')}
    $stage='credentials'
    Write-PharmacyAttempt -Status 'running'
    . (Join-Path $PSScriptRoot 'lib/collector-credential-store.ps1')
    $config=ConvertFrom-StringData ((Get-Content -LiteralPath (Join-Path $CredentialRoot '.env.collector.local') -Encoding UTF8 | Where-Object {$_.Trim() -and -not $_.TrimStart().StartsWith('#')}) -join "`n")
    $credentials=Read-CollectorCredentialStore -Path (Join-Path $CredentialRoot '.collector-credentials.local.json') -ExpectedProjectRef 'mpladsyzilmgiefejpkq'
    if($null -eq $credentials){throw 'Protected credentials unavailable'}
    if(-not $PythonPath){$PythonPath=Join-Path $env:LOCALAPPDATA 'Python/pythoncore-3.14-64/python.exe'}
    if(-not (Test-Path -LiteralPath $PythonPath)){throw 'Python unavailable'}
    $stage='checkpoint'
    $pointer=Join-Path $stateRoot 'active.txt'
    if(Test-Path -LiteralPath $pointer){
        $batch=(Get-Content -LiteralPath $pointer -Raw).Trim()
        if($batch -notmatch '^[a-f0-9]{32}$'){throw 'Invalid checkpoint'}
    } else {
        $batch=[Guid]::NewGuid().ToString('N')
        [IO.File]::WriteAllText($pointer,$batch)
    }
    $directory=Join-Path $stateRoot $batch
    $certificate=New-TemporaryFile
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config/certificates/supabase-prod-ca-2021.crt') -Destination $certificate.FullName
    $password=[Uri]::EscapeDataString($credentials.DatabasePassword)
    $ca=[Uri]::EscapeDataString($certificate.FullName)
    $env:DATABASE_URL="postgresql://collector_querido_diario.mpladsyzilmgiefejpkq:${password}@$($config.COLLECTOR_POOLER_HOST):5432/postgres?sslmode=verify-full&sslrootcert=${ca}"
    $env:APP_ENV='development'; $env:LOG_LEVEL='WARNING'; $env:PYTHONDONTWRITEBYTECODE='1'
    $env:PYTHONPATH=Join-Path $projectRoot 'workers/collectors/src'
    $env:PERSISTENCE_MODE='postgres-supabase'
    $env:SUPABASE_URL='https://mpladsyzilmgiefejpkq.supabase.co'
    $env:SUPABASE_PUBLISHABLE_KEY=$config.SUPABASE_PUBLISHABLE_KEY
    $env:SUPABASE_WORKLOAD_EMAIL=$config.SUPABASE_WORKLOAD_EMAIL
    $env:SUPABASE_WORKLOAD_PASSWORD=$credentials.WorkloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET='raw-artifacts'
    $origin=if($Scheduled){'windows_scheduler'}else{'manual'}
    $stage='collector'
    Write-PharmacyAttempt -Status 'running'
    $output=@(& $PythonPath -X utf8 -B -m barreiras_collectors.commands.refresh_fns_pharmacy --year $Year --directory $directory --max-requests 20 --execution-origin $origin)
    $resultCode=$LASTEXITCODE
    $stage='report'
    $report=$null
    foreach($line in $output){
        try {$candidate=$line | ConvertFrom-Json; if($candidate.event -eq 'pharmacy_refresh'){$report=$candidate}} catch {}
    }
    if($null -eq $report){throw 'Missing completion report'}
    if($report.status -notin @('complete','empty','partial','failed')){throw 'Invalid completion status'}
    if(($resultCode -eq 0) -ne ($report.status -in @('complete','empty'))){throw 'Inconsistent completion status'}
    # Only sanitized, allowlisted fields leave this wrapper.
    $safe=[ordered]@{event='pharmacy_refresh';year=$Year;status=$report.status}
    foreach($field in @('pages_preserved','verified_documents','published_scopes','unchanged_scopes','pending_scopes','missing_scopes','excluded_scopes')){
        if($report.PSObject.Properties[$field]){$safe[$field]=[int]$report.$field}
    }
    $json=$safe | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $stateRoot 'latest.json'),$json)
    Write-Output $json
    # Partial acquisition resumes the same batch. Completed acquisition with
    # editorial pendencies remains preserved, but the next day checks new data.
    if(($resultCode -eq 0 -and $report.status -in @('complete','empty')) -or
       ($resultCode -eq 2 -and ($report.pending_scopes -gt 0 -or $report.missing_scopes -gt 0))){
        Remove-Item -LiteralPath $pointer
    }
    Write-PharmacyAttempt -Status $report.status -Finished
} catch {
    $failureLine=$_.InvocationInfo.ScriptLineNumber
    $status='failed'; $reason='helper_failed'; $resultCode=1
    if($stage -eq 'source_lock' -and $_.Exception -is [TimeoutException]){
        $status='deferred'; $reason='source_busy'; $resultCode=75
    }
    try {Write-PharmacyAttempt -Status $status -Reason $reason -Finished} catch {}
    Write-Output (@{event='pharmacy_refresh_helper';year=$Year;status=$status;stage=$stage;reason=$reason;line=$failureLine} | ConvertTo-Json -Compress)
} finally {
    try {
        foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
        if($null -ne $certificate){Remove-Item -LiteralPath $certificate.FullName -Force}
    } catch {
        $resultCode=1; $stage='cleanup'
        try {Write-PharmacyAttempt -Status 'failed' -Reason 'cleanup_failed' -Finished} catch {}
        Write-Output (@{event='pharmacy_refresh_helper';year=$Year;status='failed';stage=$stage;reason='cleanup_failed'} | ConvertTo-Json -Compress)
    } finally {
        if($null -ne $runLock){$runLock.Dispose()}
        $credentials=$null; $config=$null; $password=$null
    }
}
exit $resultCode
