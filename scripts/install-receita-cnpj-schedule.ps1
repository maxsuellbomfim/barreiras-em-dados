param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')]
    [string]$WeeklyAt = "03:23",
    [switch]$StartNow
)

# Toda segunda-feira: se a Receita publicou mês novo (ou há CNPJ novo nos
# contratos), baixa a base e preserva o extrato; senão, só registra que pulou.

$ErrorActionPreference = "Stop"
$taskName = "Barreiras360-ReceitaCNPJ"
$projectRoot = Split-Path -Parent $PSScriptRoot
$wrapperPath = Join-Path $PSScriptRoot "run-receita-cnpj.ps1"
foreach ($required in @(
    $wrapperPath,
    (Join-Path $projectRoot ".collector-credentials.local.json"),
    (Join-Path $projectRoot ".env.collector.local")
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Arquivo necessário não localizado: $required"
    }
}

$powerShellPath = Join-Path $PSHOME "powershell.exe"
$arguments = @(
    "-NoProfile"
    "-NonInteractive"
    "-WindowStyle Hidden"
    "-ExecutionPolicy Bypass"
    "-File `"$wrapperPath`""
) -join " "
$action = New-ScheduledTaskAction `
    -Execute $powerShellPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $WeeklyAt
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description (
        "Cadastro CNPJ da Receita (ADR 0093) para os contratados de Barreiras; " +
        "baixa ~7 GB só quando há mês novo ou CNPJ novo."
    )
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if ($StartNow) {
    Start-ScheduledTask -TaskName $taskName
}
Write-Host "Tarefa $taskName registrada para $currentUser (segundas, $WeeklyAt)." `
    -ForegroundColor Green
