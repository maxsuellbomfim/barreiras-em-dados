function Assert-TcmBaRequestsPerMinute {
    [CmdletBinding()]
    param(
        [object]$RequestsPerMinute = 30
    )

    $candidate = $null
    $integerTypeNames = @(
        "Byte", "SByte", "Int16", "UInt16", "Int32", "UInt32",
        "Int64", "UInt64"
    )
    if ($null -eq $RequestsPerMinute -or $RequestsPerMinute -is [bool]) {
        throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
    }
    if ($RequestsPerMinute -is [string]) {
        $text = $RequestsPerMinute.Trim()
        if ($text -notmatch '^\d+$') {
            throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
        }
        try {
            $candidate = [long]::Parse(
                $text,
                [Globalization.CultureInfo]::InvariantCulture
            )
        }
        catch {
            throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
        }
    }
    elseif ($integerTypeNames -contains $RequestsPerMinute.GetType().Name) {
        try {
            $candidate = [long]$RequestsPerMinute
        }
        catch {
            throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
        }
    }
    else {
        throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
    }

    if ($candidate -lt 1 -or $candidate -gt 30) {
        throw "RequestsPerMinute deve ser um inteiro numérico entre 1 e 30."
    }
    return $candidate
}

function Assert-TcmBaReplayApproval {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Events,
        [int]$ExpectedDocuments
    )

    if ($ExpectedDocuments -lt 0) {
        throw "ExpectedDocuments não pode ser negativo."
    }

    $completedEvents = @(
        $Events | Where-Object {
            $_.event -eq "collector_tcm_ba_month_completed"
        }
    )
    if ($completedEvents.Count -ne 1) {
        throw (
            "A aprovação exige exatamente um evento " +
            "collector_tcm_ba_month_completed."
        )
    }

    $event = $completedEvents[0]
    if ($event.coverage_status -ne "complete") {
        throw "O evento final do TCM-BA não tem coverage_status complete."
    }

    $rawDocuments = $event.documents
    if (
        $null -eq $rawDocuments -or
        $rawDocuments -is [bool] -or
        $rawDocuments -is [string] -or
        $rawDocuments.GetType().Name -notin @(
            "Byte", "SByte", "Int16", "UInt16", "Int32", "UInt32",
            "Int64", "UInt64", "Decimal", "Double", "Single"
        )
    ) {
        throw "documents deve ser um inteiro numérico positivo."
    }

    try {
        $decimalDocuments = [decimal]$rawDocuments
        if ($decimalDocuments -ne [decimal]::Truncate($decimalDocuments)) {
            throw "documents não é inteiro."
        }
        $documents = [long]$decimalDocuments
    }
    catch {
        throw "documents deve ser um inteiro numérico positivo."
    }
    if ($documents -le 0) {
        throw "O evento final do TCM-BA deve ter documents maior que zero."
    }

    if ($ExpectedDocuments -gt 0 -and $documents -ne $ExpectedDocuments) {
        throw (
            "A competência não fechou com a contagem esperada de " +
            "$ExpectedDocuments documentos."
        )
    }

    return $true
}
