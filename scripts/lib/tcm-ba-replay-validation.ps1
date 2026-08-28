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
function ConvertTo-TcmBaNonNegativeInteger {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$Value,
        [string]$FieldName
    )

    if (
        $null -eq $Value -or
        $Value -is [bool] -or
        $Value -is [string] -or
        $Value.GetType().Name -notin @(
            "Byte", "SByte", "Int16", "UInt16", "Int32", "UInt32",
            "Int64", "UInt64", "Decimal", "Double", "Single"
        )
    ) {
        throw "$FieldName deve ser um inteiro numérico não negativo."
    }

    try {
        $decimalValue = [decimal]$Value
        if ($decimalValue -ne [decimal]::Truncate($decimalValue)) {
            throw "$FieldName não é inteiro."
        }
        $integerValue = [long]$decimalValue
    }
    catch {
        throw "$FieldName deve ser um inteiro numérico não negativo."
    }
    if ($integerValue -lt 0) {
        throw "$FieldName deve ser um inteiro numérico não negativo."
    }
    return $integerValue
}

function Assert-TcmBaDocumentBatchApproval {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Events,
        [string]$ExpectedCompetence,
        [ValidateRange(1, 5)]
        [int]$MaxDocuments
    )

    if ($ExpectedCompetence -notmatch '^(0[1-9]|1[0-2])/\d{4}$') {
        throw "ExpectedCompetence deve usar o formato MM/AAAA."
    }

    $completedEvents = @(
        $Events | Where-Object {
            $_.event -eq "collector_tcm_ba_documents_completed"
        }
    )
    if ($completedEvents.Count -ne 1) {
        throw (
            "A aprovação exige exatamente um evento " +
            "collector_tcm_ba_documents_completed."
        )
    }

    $event = $completedEvents[0]
    if ($event.competence -ne $ExpectedCompetence) {
        throw "A competência do evento final diverge da solicitada."
    }

    $expected = ConvertTo-TcmBaNonNegativeInteger -Value $event.expected_documents -FieldName "expected_documents"
    $downloaded = ConvertTo-TcmBaNonNegativeInteger -Value $event.downloaded_documents -FieldName "downloaded_documents"
    $preserved = ConvertTo-TcmBaNonNegativeInteger -Value $event.preserved_documents -FieldName "preserved_documents"
    $remaining = ConvertTo-TcmBaNonNegativeInteger -Value $event.remaining_documents -FieldName "remaining_documents"

    if ($expected -le 0) {
        throw "expected_documents deve ser maior que zero."
    }
    if ($downloaded -le 0 -or $downloaded -gt $MaxDocuments) {
        throw "O lote deve preservar entre 1 e MaxDocuments PDFs."
    }
    if ($preserved -lt $downloaded -or $preserved -gt $expected) {
        throw "A contagem cumulativa de PDFs preservados é inválida."
    }
    if (($preserved + $remaining) -ne $expected) {
        throw "Preservados e restantes não recompõem o total esperado."
    }

    $expectedCoverage = if ($remaining -eq 0) { "complete" } else { "partial" }
    if ($event.coverage_status -ne $expectedCoverage) {
        throw "coverage_status diverge dos contadores documentais."
    }

    return $true
}
