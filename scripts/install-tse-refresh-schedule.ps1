param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')][string]$DailyAt = '06:17'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
foreach ($file in @('.collector-credentials.local.json', '.env.collector.local')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $file))) {
        throw 'Collector configuration unavailable'
    }
}
$wrapper = Join-Path $PSScriptRoot 'run-tse-votes.ps1'
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`" -Anos 2026"
$powerShellPath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
. (Join-Path $PSScriptRoot 'lib/hidden-task-action.ps1')
$action = New-HiddenPowerShellTaskAction -PowerShellPath $powerShellPath -Arguments $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Atualiza votos TSE 2026 em Barreiras, por cargo e turno. Resultado eleitoral nao altera mandato. Requer computador e sessao Windows disponiveis; falhas registradas no controle central.'
Register-ScheduledTask -TaskName 'Barreiras360-TseRefresh-2026' -InputObject $task -Force | Out-Null
Write-Output "TSE 2026: tarefa diaria registrada para $DailyAt, sem janela."
