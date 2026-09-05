param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')]
    [string]$DailyAt = "06:17",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$taskName = "Barreiras360-TCMBA-MonthlyCatalog"
$projectRoot = Split-Path -Parent $PSScriptRoot
$wrapperPath = Join-Path $PSScriptRoot "run-tcm-ba-monthly-catalog.ps1"
$credentialStorePath = Join-Path $projectRoot ".collector-credentials.local.json"
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
if (-not (Test-Path -LiteralPath $wrapperPath)) {
    throw "O wrapper mensal do TCM-BA não foi localizado."
}
if (-not (Test-Path -LiteralPath $credentialStorePath)) {
    throw "O cofre DPAPI do coletor não foi localizado."
}
if (-not (Test-Path -LiteralPath $localConfigPath)) {
    throw "A configuração local do coletor não foi localizada."
}

$powerShellPath = Join-Path $PSHOME "powershell.exe"
$arguments = @(
    "-NoProfile"
    "-NonInteractive"
    "-WindowStyle Hidden"
    "-ExecutionPolicy Bypass"
    "-File `"$wrapperPath`""
    "-AutomaticClosedMonth"
    "-RequestsPerMinute 30"
) -join " "
$action = New-ScheduledTaskAction `
    -Execute $powerShellPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)
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
        "Verifica diariamente o último mês fechado do catálogo TCM-BA; " +
        "não sobrepõe execuções e mantém indisponibilidade da fonte visível."
    )
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if ($StartNow) {
    Start-ScheduledTask -TaskName $taskName
}
$registered = Get-ScheduledTask -TaskName $taskName
Write-Host "Tarefa $($registered.TaskName) registrada para $currentUser." `
    -ForegroundColor Green
Write-Host (
    "Cadência diária às $DailyAt; sem sobreposição; retoma horários " +
    "perdidos; 30 RPM; limite de 90 minutos."
)
