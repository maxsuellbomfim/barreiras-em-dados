param(
    [string]$PythonPath = ""
)

# ADR 0093: o compartilhamento de dados abertos do CNPJ da Receita recusa
# conexões dos servidores do GitHub (fora do Brasil); a coleta roda nesta
# máquina, com as mesmas credenciais protegidas (DPAPI) dos coletores locais.

$ErrorActionPreference = "Stop"
$projectRef = "mpladsyzilmgiefejpkq"
$collectorUser = "collector_querido_diario.$projectRef"
$projectRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
$credentialStorePath = Join-Path $projectRoot ".collector-credentials.local.json"
$sslRootCertificatePath = $null
. (Join-Path $PSScriptRoot "lib\collector-credential-store.ps1")

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
    $bundled = Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python não foi localizado."
}

Write-Host "Coleta local do cadastro CNPJ da Receita" -ForegroundColor Green
$localConfig = Read-LocalCollectorConfig
$poolerHost = $localConfig.COLLECTOR_POOLER_HOST
$publishableKey = $localConfig.SUPABASE_PUBLISHABLE_KEY
$workloadEmail = $localConfig.SUPABASE_WORKLOAD_EMAIL
if (-not $poolerHost.EndsWith(".pooler.supabase.com")) {
    throw "COLLECTOR_POOLER_HOST não pertence ao pooler do Supabase."
}
if (-not $publishableKey.StartsWith("sb_publishable_")) {
    throw "SUPABASE_PUBLISHABLE_KEY local é inválida."
}

$credentialStore = Read-CollectorCredentialStore `
    -Path $credentialStorePath `
    -ExpectedProjectRef $projectRef
if (-not $credentialStore) {
    throw "O cofre DPAPI do coletor não foi localizado."
}
$databasePassword = $credentialStore.DatabasePassword
$workloadPassword = $credentialStore.WorkloadPassword

try {
    $bundledCa = Join-Path $projectRoot "config\certificates\supabase-prod-ca-2021.crt"
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
            $output = @(
                & $python -B -m barreiras_collectors.commands.collect_receita_cnpj 2>&1
            )
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
    $terminal = $output | Where-Object {
        $_.ToString() -match '"event":\s*"receita_cnpj_(completed|skipped)"'
    }
    if (-not $terminal) {
        throw "O coletor não produziu o evento final do cadastro CNPJ."
    }
    Write-Host "RECEITA_CNPJ_OK" -ForegroundColor Green
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
}
