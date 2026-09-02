param(
    [string]$MonthFrom = "2023-04",
    [string]$MonthTo = "2023-04",
    [int]$ExpectedDocuments = 1824,
    [object]$RequestsPerMinute = 30,
    [string]$PythonPath = "",
    [switch]$AutomaticClosedMonth
)

$ErrorActionPreference = "Stop"
$projectRef = "mpladsyzilmgiefejpkq"
$collectorUser = "collector_querido_diario.$projectRef"
$projectRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
$credentialStorePath = Join-Path $projectRoot `
    ".collector-credentials.local.json"
$sslRootCertificatePath = $null
$credentialHelperPath = Join-Path $PSScriptRoot `
    "lib\collector-credential-store.ps1"
. $credentialHelperPath
$validationHelperPath = Join-Path $PSScriptRoot `
    "lib\tcm-ba-replay-validation.ps1"
. $validationHelperPath

$RequestsPerMinute = Assert-TcmBaRequestsPerMinute -RequestsPerMinute $RequestsPerMinute

function Read-LocalCollectorConfig {
    if (-not (Test-Path -LiteralPath $localConfigPath)) {
        throw (
            "Crie .env.collector.local com COLLECTOR_POOLER_HOST, " +
            "SUPABASE_PUBLISHABLE_KEY e SUPABASE_WORKLOAD_EMAIL."
        )
    }
    $lines = Get-Content -LiteralPath $localConfigPath -Encoding UTF8 |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            -not $_.TrimStart().StartsWith("#")
        }
    return ConvertFrom-StringData ($lines -join [Environment]::NewLine)
}

function Find-Python {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        return (Resolve-Path -LiteralPath $PythonPath).Path
    }
    $bundled = Join-Path $env:LOCALAPPDATA `
        "Python\pythoncore-3.14-64\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python não foi localizado."
}

function Read-CompletedEvents {
    param([object[]]$Output)

    $events = @()
    foreach ($line in $Output) {
        $text = $line.ToString().Trim()
        if (-not $text.StartsWith("{")) {
            continue
        }
        try {
            $event = $text | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($event.event -eq "collector_tcm_ba_month_completed") {
            $events += $event
        }
    }
    if ($events.Count -eq 0) {
        throw "O coletor não produziu o evento final do TCM-BA."
    }
    return $events
}

function Read-AutomaticEvents {
    param([object[]]$Output)

    $events = @()
    foreach ($line in $Output) {
        $text = $line.ToString().Trim()
        if (-not $text.StartsWith("{")) {
            continue
        }
        try {
            $event = $text | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($event.event -in @(
            "collector_tcm_ba_month_completed",
            "collector_tcm_ba_month_skipped"
        )) {
            $events += $event
        }
    }
    if ($events.Count -eq 0) {
        throw "O coletor automático não produziu um evento terminal."
    }
    return $events
}

if ($AutomaticClosedMonth) {
    foreach ($parameterName in @("MonthFrom", "MonthTo", "ExpectedDocuments")) {
        if ($PSBoundParameters.ContainsKey($parameterName)) {
            throw "AutomaticClosedMonth não aceita $parameterName explícito."
        }
    }
}
else {
    if (
        $MonthFrom -notmatch '^\d{4}-(0[1-9]|1[0-2])$' -or
        $MonthTo -notmatch '^\d{4}-(0[1-9]|1[0-2])$'
    ) {
        throw "As competências devem usar o formato AAAA-MM."
    }
    if ($ExpectedDocuments -gt 0 -and $MonthFrom -ne $MonthTo) {
        throw "ExpectedDocuments só pode ser usado com uma competência exata."
    }
}

Write-Host "Replay local seguro do catálogo mensal do TCM-BA" -ForegroundColor Green
Write-Host "As senhas ficam protegidas pelo usuário atual do Windows."
$localConfig = Read-LocalCollectorConfig
$poolerHost = $localConfig.COLLECTOR_POOLER_HOST
$publishableKey = $localConfig.SUPABASE_PUBLISHABLE_KEY
$workloadEmail = $localConfig.SUPABASE_WORKLOAD_EMAIL
if (-not $poolerHost.EndsWith(".pooler.supabase.com")) {
    throw "COLLECTOR_POOLER_HOST não pertence ao pooler do Supabase."
}
if (
    -not $publishableKey.StartsWith("sb_publishable_") -or
    $publishableKey.Length -lt 24
) {
    throw "SUPABASE_PUBLISHABLE_KEY local é inválida."
}
if ($workloadEmail.Split("@").Count -ne 2) {
    throw "SUPABASE_WORKLOAD_EMAIL local é inválido."
}

$credentialStore = Read-CollectorCredentialStore `
    -Path $credentialStorePath `
    -ExpectedProjectRef $projectRef
if ($credentialStore) {
    Write-Host "Credenciais protegidas do Windows carregadas." `
        -ForegroundColor Cyan
    $databasePassword = $credentialStore.DatabasePassword
    $workloadPassword = $credentialStore.WorkloadPassword
}
else {
    $databasePassword = $localConfig.COLLECTOR_DATABASE_PASSWORD
    $workloadPassword = $localConfig.SUPABASE_WORKLOAD_PASSWORD
}
if ([string]::IsNullOrWhiteSpace($databasePassword)) {
    $databasePassword = Convert-CollectorSecureStringToPlainText (
        Read-Host "Senha PostgreSQL do coletor" -AsSecureString
    )
}
if ([string]::IsNullOrWhiteSpace($workloadPassword)) {
    $workloadPassword = Convert-CollectorSecureStringToPlainText (
        Read-Host "Senha do usuário técnico do Storage" -AsSecureString
    )
}

try {
    if ($databasePassword.Length -lt 24) {
        throw "A senha PostgreSQL deve ter ao menos 24 caracteres."
    }
    if ($workloadPassword.Length -lt 24) {
        throw "A senha do usuário técnico deve ter ao menos 24 caracteres."
    }
    $bundledCa = Join-Path $projectRoot `
        "config\certificates\supabase-prod-ca-2021.crt"
    if (-not (Test-Path -LiteralPath $bundledCa)) {
        throw "O certificado CA oficial do Supabase não foi localizado."
    }
    $sslRootCertificatePath = Join-Path ([IO.Path]::GetTempPath()) (
        "barreiras-" + [IO.Path]::GetRandomFileName() + ".crt"
    )
    Copy-Item -LiteralPath $bundledCa -Destination $sslRootCertificatePath

    $encodedDatabasePassword = [Uri]::EscapeDataString($databasePassword)
    $encodedCertificate = [Uri]::EscapeDataString($sslRootCertificatePath)
    $env:DATABASE_URL = (
        "postgresql://${collectorUser}:${encodedDatabasePassword}" +
        "@${poolerHost}:5432/postgres" +
        "?sslmode=verify-full&sslrootcert=${encodedCertificate}"
    )
    $env:APP_ENV = "development"
    $env:LOG_LEVEL = "INFO"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = "workers/collectors/src"
    $env:PERSISTENCE_MODE = "postgres-supabase"
    $env:SUPABASE_URL = "https://$projectRef.supabase.co"
    $env:SUPABASE_PUBLISHABLE_KEY = $publishableKey
    $env:SUPABASE_WORKLOAD_EMAIL = $workloadEmail
    $env:SUPABASE_WORKLOAD_PASSWORD = $workloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET = "raw-artifacts"

    $python = Find-Python
    Push-Location $projectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            if ($AutomaticClosedMonth) {
                $output = @(
                    & $python -B -m `
                        barreiras_collectors.commands.collect_tcm_ba_monthly_catalog `
                        --automatic-closed-month `
                        --requests-per-minute $RequestsPerMinute 2>&1
                )
            }
            else {
                $output = @(
                    & $python -B -m `
                        barreiras_collectors.commands.collect_tcm_ba_monthly_catalog `
                        --month-from $MonthFrom `
                        --month-to $MonthTo `
                        --requests-per-minute $RequestsPerMinute 2>&1
                )
            }
            $nativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($nativeExitCode -ne 0) {
        throw "O coletor terminou com código $nativeExitCode."
    }
    if ($AutomaticClosedMonth) {
        $events = @(Read-AutomaticEvents -Output $output)
        $null = Assert-TcmBaAutomaticCatalogOutcome -Events $events
        Write-Host "TCM_BA_AUTOMATIC_CHECK_COMPLETED" -ForegroundColor Green
    }
    else {
        $events = @(Read-CompletedEvents -Output $output)
        $null = Assert-TcmBaReplayApproval `
            -Events $events `
            -ExpectedDocuments $ExpectedDocuments
        Write-Host "TCM_BA_REPLAY_APROVADO" -ForegroundColor Green
    }
}
finally {
    foreach ($name in @(
        "DATABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_WORKLOAD_EMAIL",
        "SUPABASE_WORKLOAD_PASSWORD"
    )) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    if (
        -not [string]::IsNullOrWhiteSpace($sslRootCertificatePath) -and
        (Test-Path -LiteralPath $sslRootCertificatePath)
    ) {
        Remove-Item -LiteralPath $sslRootCertificatePath -Force
    }
    $databasePassword = $null
    $workloadPassword = $null
    $credentialStore = $null
    $encodedDatabasePassword = $null
    $env:DATABASE_URL = $null
}
