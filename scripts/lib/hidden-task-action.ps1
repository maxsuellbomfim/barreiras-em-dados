function New-HiddenPowerShellTaskAction {
    # No Windows 11 o terminal padrão é o Windows Terminal, que ignora
    # -WindowStyle Hidden e abre uma aba a cada execução agendada. O
    # conhost.exe --headless executa o PowerShell sem janela nenhuma.
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PowerShellPath,
        [Parameter(Mandatory)][string]$Arguments,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )
    $conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
    if (-not (Test-Path -LiteralPath $conhost)) {
        return New-ScheduledTaskAction -Execute $PowerShellPath -Argument $Arguments -WorkingDirectory $WorkingDirectory
    }
    New-ScheduledTaskAction `
        -Execute $conhost `
        -Argument "--headless `"$PowerShellPath`" $Arguments" `
        -WorkingDirectory $WorkingDirectory
}
