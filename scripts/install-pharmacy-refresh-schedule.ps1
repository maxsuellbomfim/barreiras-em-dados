param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')][string]$DailyAt='07:43',
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [switch]$StartNow
)
$ErrorActionPreference='Stop'
$taskName='Barreiras360-PharmacyRefresh'
$projectRoot=Split-Path -Parent $PSScriptRoot
$wrapper=Join-Path $PSScriptRoot 'run-pharmacy-refresh.ps1'
$CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
if($CredentialRoot.Contains('"')){throw 'Invalid configuration path'}
foreach($file in @('.collector-credentials.local.json','.env.collector.local')){
    if(-not (Test-Path -LiteralPath (Join-Path $CredentialRoot $file))){throw 'Collector configuration unavailable'}
}
$arguments="-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`" -CredentialRoot `"$CredentialRoot`" -Scheduled"
$action=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $arguments -WorkingDirectory $projectRoot
$trigger=New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task=New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Confere Farmacia Popular do ano corrente; cofre Windows, retomada e validacao antes de publicar. Requer computador e sessao Windows disponiveis.'
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if($StartNow){Start-ScheduledTask -TaskName $taskName}
Write-Output "Tarefa $taskName registrada: diaria $DailyAt, silenciosa, ano corrente."
