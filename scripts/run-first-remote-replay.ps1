param(
    [string]$Since = "2026-06-10",
    [string]$Until = "2026-06-10",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRef = "mpladsyzilmgiefejpkq"
$collectorUser = "collector_querido_diario.$projectRef"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Convert-SecureValueToPlainText {
    param([Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Find-Python {
    if ($PythonPath) {
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

function Read-CompletedEvent {
    param([object[]]$Output)

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
        if ($event.event -eq "collector_window_completed") {
            return $event
        }
    }
    throw "O coletor não produziu o evento final esperado."
}

function Invoke-Collector {
    param(
        [string]$Python,
        [string]$Label
    )

    Write-Host ""
    Write-Host $Label -ForegroundColor Cyan
    $output = @(
        & $Python -B -m `
            barreiras_collectors.commands.collect_querido_diario `
            --since $Since `
            --until $Until `
            --page-size 100 2>&1
    )
    $output | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "O coletor terminou com código $LASTEXITCODE."
    }
    return Read-CompletedEvent -Output $output
}

Write-Host "Replay remoto seguro do Querido Diário" -ForegroundColor Green
Write-Host "As senhas serão usadas apenas na memória deste PowerShell."
Write-Host "Nada será gravado no chat, no Git ou em arquivo .env."
Write-Host ""
Write-Host "No Supabase, abra Connect > Session pooler e copie a URI."
Write-Host "Mantenha o trecho [YOUR-PASSWORD]; a senha será pedida separadamente."

$connectionTemplate = (Read-Host "URI do Session pooler").Trim()
$connectionMatch = [regex]::Match(
    $connectionTemplate,
    "^postgres(?:ql)?://[^@]+@(?<host>[^:/?#]+):(?<port>\d+)/(?<database>[^?]+)"
)
if (-not $connectionMatch.Success) {
    throw "A URI do Session pooler não possui o formato esperado."
}

$poolerHost = $connectionMatch.Groups["host"].Value
$poolerPort = $connectionMatch.Groups["port"].Value
$databaseName = $connectionMatch.Groups["database"].Value
if (
    -not $poolerHost.EndsWith(".pooler.supabase.com") -or
    $poolerPort -ne "5432" -or
    $databaseName -ne "postgres" -or
    -not $connectionTemplate.Contains($projectRef)
) {
    throw "Use o Session pooler do projeto Barreiras em Dados, na porta 5432."
}

$databasePasswordSecure = Read-Host `
    "Senha PostgreSQL da role collector_querido_diario" -AsSecureString
$publishableKey = (Read-Host "Supabase publishable key (sb_publishable_...)").Trim()
$workloadEmail = (Read-Host "E-mail técnico do coletor no Supabase Auth").Trim()
$workloadPasswordSecure = Read-Host `
    "Senha do usuário técnico do Supabase Auth" -AsSecureString

$databasePassword = Convert-SecureValueToPlainText $databasePasswordSecure
$workloadPassword = Convert-SecureValueToPlainText $workloadPasswordSecure
try {
    if ($databasePassword.Length -lt 24) {
        throw "A senha PostgreSQL deve ter ao menos 24 caracteres."
    }
    if (
        -not $publishableKey.StartsWith("sb_publishable_") -or
        $publishableKey.Length -lt 24
    ) {
        throw "A publishable key não possui o formato atual."
    }
    if (
        $workloadEmail.Split("@").Count -ne 2 -or
        [string]::IsNullOrWhiteSpace($workloadEmail)
    ) {
        throw "O e-mail técnico é inválido."
    }
    if ($workloadPassword.Length -lt 24) {
        throw "A senha do usuário técnico deve ter ao menos 24 caracteres."
    }

    $encodedDatabasePassword = [Uri]::EscapeDataString($databasePassword)
    $databaseUrl = (
        "postgresql://${collectorUser}:${encodedDatabasePassword}" +
        "@${poolerHost}:${poolerPort}/${databaseName}?sslmode=verify-full"
    )

    $env:APP_ENV = "development"
    $env:LOG_LEVEL = "INFO"
    $env:PYTHONPATH = "workers/collectors/src"
    $env:PERSISTENCE_MODE = "postgres-supabase"
    $env:DATABASE_URL = $databaseUrl
    $env:SUPABASE_URL = "https://$projectRef.supabase.co"
    $env:SUPABASE_PUBLISHABLE_KEY = $publishableKey
    $env:SUPABASE_WORKLOAD_EMAIL = $workloadEmail
    $env:SUPABASE_WORKLOAD_PASSWORD = $workloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET = "raw-artifacts"

    $python = Find-Python
    Push-Location $projectRoot
    try {
        $first = Invoke-Collector -Python $python -Label "Primeira execução"
        $second = Invoke-Collector -Python $python -Label "Replay idempotente"
    }
    finally {
        Pop-Location
    }

    $firstTotal = [int]$first.inserted_records + [int]$first.existing_records
    if (
        $firstTotal -ne 2 -or
        [int]$second.inserted_records -ne 0 -or
        [int]$second.existing_records -ne 2
    ) {
        throw (
            "O resultado não corresponde ao contrato esperado: " +
            "primeira execução total=2; replay inseridos=0, existentes=2."
        )
    }

    Write-Host ""
    Write-Host "REPLAY_REMOTO_APROVADO" -ForegroundColor Green
    Write-Host "Volte ao Codex e diga: replay concluído."
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
    $databasePassword = $null
    $workloadPassword = $null
    $databaseUrl = $null
}
