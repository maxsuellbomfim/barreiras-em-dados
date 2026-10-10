# Atualiza as tarefas Barreiras360-* já registradas para rodar sem janela:
# troca "powershell.exe <args>" por "conhost.exe --headless powershell.exe
# <args>". Horários, gatilhos, argumentos e credenciais não mudam. Rodar de
# novo não altera tarefas já convertidas.
$ErrorActionPreference = 'Stop'
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
if (-not (Test-Path -LiteralPath $conhost)) { throw 'conhost.exe indisponível' }
foreach ($task in Get-ScheduledTask -TaskName 'Barreiras360-*') {
    $changed = $false
    $actions = foreach ($action in $task.Actions) {
        if ($action.Execute -like '*powershell.exe') {
            $changed = $true
            New-ScheduledTaskAction `
                -Execute $conhost `
                -Argument "--headless `"$($action.Execute)`" $($action.Arguments)" `
                -WorkingDirectory $action.WorkingDirectory
        } else {
            $action
        }
    }
    if ($changed) {
        Set-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Action $actions | Out-Null
        Write-Output "Sem janela: $($task.TaskName)"
    } else {
        Write-Output "Já sem janela: $($task.TaskName)"
    }
}
