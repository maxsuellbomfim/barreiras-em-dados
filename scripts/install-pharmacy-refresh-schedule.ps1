param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')][string]$DailyAt='07:43',
    [string]$CredentialRoot=(Split-Path -Parent $PSScriptRoot),
    [ValidateRange(2021,2100)][int]$HistoricalYear,
    [ValidateSet('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')][string]$DayOfWeek='Saturday',
    [switch]$StartNow
)
$ErrorActionPreference='Stop'
$taskName='Barreiras360-PharmacyRefresh'
if($HistoricalYear){
    if($HistoricalYear -ge (Get-Date).Year){throw 'Historical year must be closed'}
    $taskName += "-History-$HistoricalYear"
}
$projectRoot=Split-Path -Parent $PSScriptRoot
$wrapper=Join-Path $PSScriptRoot 'run-pharmacy-refresh.ps1'
$CredentialRoot=(Resolve-Path -LiteralPath $CredentialRoot).Path
if($CredentialRoot.Contains('"')){throw 'Invalid configuration path'}
foreach($file in @('.collector-credentials.local.json','.env.collector.local')){
    if(-not (Test-Path -LiteralPath (Join-Path $CredentialRoot $file))){throw 'Collector configuration unavailable'}
}
$arguments="-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`" -CredentialRoot `"$CredentialRoot`" -Scheduled"
if($HistoricalYear){$arguments += " -Year $HistoricalYear"}
$powerShellPath=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
if(-not (Test-Path -LiteralPath $powerShellPath)){throw 'Windows PowerShell unavailable'}
$action=New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory $projectRoot
$trigger=New-ScheduledTaskTrigger -Daily -At $DailyAt
if($HistoricalYear){$trigger=New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek $DayOfWeek -At $DailyAt}
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$scope=if($HistoricalYear){"historico $HistoricalYear, semanal $DayOfWeek"}else{'ano corrente, diaria'}
$task=New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Confere Farmacia Popular: $scope; cofre Windows, retomada e validacao antes de publicar. Requer computador e sessao Windows disponiveis."
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
if($StartNow){Start-ScheduledTask -TaskName $taskName}
Write-Output "Tarefa $taskName registrada: $scope $DailyAt, silenciosa."
