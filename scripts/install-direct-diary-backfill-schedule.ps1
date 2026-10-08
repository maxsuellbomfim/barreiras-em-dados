param(
    [ValidateRange(1,24)][int]$EveryHours=1,
    [ValidateRange(1,50)][int]$Limit=15,
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [switch]$StartNow
)
# Backfill horário das edições 3353-3988 do Diário pelo executor local; o
# cron do GitHub (backfill-direct-diary.yml) continua como complemento.
$ErrorActionPreference='Stop'
$taskName='Barreiras360-DiarioBackfill'
$projectRoot=Split-Path -Parent $PSScriptRoot
$wrapper=Join-Path $PSScriptRoot 'run-direct-diary-backfill.ps1'
$CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
if($CredentialRoot.Contains('"')){throw 'Invalid configuration path'}
foreach($file in @('.collector-credentials.local.json','.env.collector.local')){
    if(-not (Test-Path -LiteralPath (Join-Path $CredentialRoot $file))){throw 'Collector configuration unavailable'}
}
$arguments="-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`" -CredentialRoot `"$CredentialRoot`" -Limit $Limit -Scheduled"
$powerShellPath=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
if(-not (Test-Path -LiteralPath $powerShellPath)){throw 'Windows PowerShell unavailable'}
$action=New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory $projectRoot
# Minuto 07: longe do cron do GitHub (minuto 37), para não disputar a partição.
$start=(Get-Date).Date.AddHours((Get-Date).Hour).AddMinutes(7)
if($start -le (Get-Date)){$start=$start.AddHours(1)}
$trigger=New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 50)
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task=New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Preserva edições antigas do Diário Oficial (3353-3988, 2021-2023) a cada $EveryHours h, $Limit por execução; cofre Windows. Requer computador e sessão Windows disponíveis."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if($StartNow){Start-ScheduledTask -TaskName $taskName}
Write-Output "Tarefa $taskName registrada: a cada $EveryHours h a partir de $($start.ToString('HH:mm')), $Limit edições por execução."
