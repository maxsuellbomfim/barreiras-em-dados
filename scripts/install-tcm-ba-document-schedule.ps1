param(
    [ValidateRange(15, 1440)]
    [int]$IntervalMinutes = 15,
    [switch]$StartNow
)
$ErrorActionPreference = "Stop"
$taskName = "Barreiras360-TCMBA-Documents"
$projectRoot = Split-Path -Parent $PSScriptRoot
$wrapperPath = Join-Path $PSScriptRoot "run-tcm-ba-document-pilot.ps1"
$credentialStorePath = Join-Path $projectRoot ".collector-credentials.local.json"
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
if (-not (Test-Path -LiteralPath $wrapperPath)) {
    throw "O wrapper documental do TCM-BA não foi localizado."
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
    "-ExecutionPolicy Bypass"
    "-File `"$wrapperPath`""
    "-AutoCompetence"
    "-MaxDocuments 5"
    "-RequestsPerMinute 30"
) -join " "
$action = New-ScheduledTaskAction `
    -Execute $powerShellPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
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
    -Description "Drena até 5 documentos TCM-BA a cada $IntervalMinutes minutos com auditoria física."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if ($StartNow) {
    Start-ScheduledTask -TaskName $taskName
}
$registered = Get-ScheduledTask -TaskName $taskName
Write-Host "Tarefa $($registered.TaskName) registrada para $currentUser." -ForegroundColor Green
Write-Host "Cadência: $IntervalMinutes minutos; sem sobreposição; retoma horários perdidos e acorda em suspensão quando conectado à energia; até 5 documentos por rodada; 30 RPM."
