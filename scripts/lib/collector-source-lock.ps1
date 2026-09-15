function Wait-CollectorSourceLock {
    [CmdletBinding()]
    [OutputType([IO.FileStream])]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$Path,

        [ValidateRange(0, 900)]
        [int]$TimeoutSeconds = 900,

        [ValidateRange(50, 5000)]
        [int]$PollMilliseconds = 500
    )

    $watch = [Diagnostics.Stopwatch]::StartNew()
    $timeoutMilliseconds = $TimeoutSeconds * 1000
    do {
        try {
            return [IO.File]::Open(
                $Path,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        }
        catch {
            # PowerShell wraps static .NET method failures in invocation errors.
            $exception = $_.Exception
            while ($null -ne $exception -and $exception -isnot [IO.IOException]) {
                $exception = $exception.InnerException
            }
            if ($null -eq $exception) { throw }

            $win32Code = $exception.HResult -band 0xffff
            # Only sharing/lock violations are contention; other failures are fatal.
            if ($win32Code -ne 32 -and $win32Code -ne 33) { throw }
        }

        $remaining = [Math]::Floor($timeoutMilliseconds - $watch.Elapsed.TotalMilliseconds)
        if ($remaining -le 0) { return $null }
        Start-Sleep -Milliseconds ([int][Math]::Min($PollMilliseconds, $remaining))
    } while ($watch.Elapsed.TotalMilliseconds -lt $timeoutMilliseconds)

    # The owner releases its stream via Dispose; never delete the shared path.
    return $null
}
