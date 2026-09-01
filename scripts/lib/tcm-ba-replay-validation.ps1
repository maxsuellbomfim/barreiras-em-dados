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

function Get-TcmBaDocumentFamilyCatchUpLimit {
    [CmdletBinding()]
    param(
        [ValidateRange(1, 5)]
        [int]$MaxDocuments
    )

    return [Math]::Min(50, 2 * $MaxDocuments)
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

function Assert-TcmBaDocumentAuditApproval {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$CollectorEvent,
        [AllowNull()]
        [object[]]$AuditEvents
    )

    if ($null -eq $CollectorEvent) {
        throw "O evento final do coletor é obrigatório para a auditoria."
    }
    $completedEvents = @(
        $AuditEvents | Where-Object {
            $_.event -eq "auditor_tcm_ba_document_batch_completed"
        }
    )
    if ($completedEvents.Count -ne 1) {
        throw (
            "A aprovação exige exatamente um evento " +
            "auditor_tcm_ba_document_batch_completed."
        )
    }
    $audit = $completedEvents[0]
    if ($audit.gate -ne "PASS") {
        throw "O auditor documental não retornou gate PASS."
    }
    if ($audit.competence -ne $CollectorEvent.competence) {
        throw "A competência auditada diverge do evento do coletor."
    }

    foreach ($field in @(
        "expected_documents",
        "downloaded_documents",
        "preserved_documents",
        "remaining_documents"
    )) {
        $collectorValue = ConvertTo-TcmBaNonNegativeInteger `
            -Value $CollectorEvent.$field -FieldName "collector.$field"
        $auditValue = ConvertTo-TcmBaNonNegativeInteger `
            -Value $audit.$field -FieldName "audit.$field"
        if ($auditValue -ne $collectorValue) {
            throw "O contador $field diverge entre coletor e auditor."
        }
    }
    if ($audit.coverage_status -ne $CollectorEvent.coverage_status) {
        throw "A cobertura diverge entre coletor e auditor."
    }

    $downloaded = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.downloaded_documents `
        -FieldName "audit.downloaded_documents"
    $artifacts = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.run_artifacts -FieldName "audit.run_artifacts"
    $prepare = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.prepare_xml -FieldName "audit.prepare_xml"
    $pdfs = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.pdfs -FieldName "audit.pdfs"
    $links = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.catalog_links -FieldName "audit.catalog_links"
    $physical = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.physical_objects_verified `
        -FieldName "audit.physical_objects_verified"
    $physicalBytes = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.physical_bytes_verified `
        -FieldName "audit.physical_bytes_verified"
    $distinctHashes = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.distinct_physical_sha256 `
        -FieldName "audit.distinct_physical_sha256"
    $currentFailures = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.current_open_failures `
        -FieldName "audit.current_open_failures"
    $null = ConvertTo-TcmBaNonNegativeInteger `
        -Value $audit.historical_open_failures `
        -FieldName "audit.historical_open_failures"

    if (
        $artifacts -ne (2 * $downloaded) -or
        $prepare -ne $downloaded -or
        $pdfs -ne $downloaded -or
        $links -ne $downloaded
    ) {
        throw "A composição e a linhagem do lote auditado são divergentes."
    }
    if (
        $physical -ne $artifacts -or
        $distinctHashes -ne $physical -or
        $physicalBytes -le 0
    ) {
        throw "A verificação física do lote auditado é incompleta."
    }
    if ($currentFailures -ne 0) {
        throw "A execução auditada ainda possui falha aberta."
    }
    return $true
}

function Assert-TcmBaDocumentTextApproval {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Events,
        [ValidateRange(1, 5)]
        [int]$MaxDocuments
    )

    $completedEvents = @(
        $Events | Where-Object {
            $_.event -eq "tcm_ba_document_text_batch_completed"
        }
    )
    if ($completedEvents.Count -ne 1) {
        throw (
            "A aprovação exige exatamente um evento " +
            "tcm_ba_document_text_batch_completed."
        )
    }
    $event = $completedEvents[0]
    $pending = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.pending_found -FieldName "pending_found"
    $processed = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.processed -FieldName "processed"
    $failed = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.failed -FieldName "failed"
    $pages = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.pages_total -FieldName "pages_total"
    $embedded = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.pages_with_embedded_text `
        -FieldName "pages_with_embedded_text"
    $ocr = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.pages_awaiting_ocr -FieldName "pages_awaiting_ocr"

    if ($pending -le 0 -or $pending -gt $MaxDocuments) {
        throw "O processamento deve encontrar entre 1 e MaxDocuments PDFs."
    }
    if ($failed -ne 0 -or $processed -ne $pending) {
        throw "Todos os PDFs encontrados devem ser processados sem falha."
    }
    if ($pages -lt $processed -or ($embedded + $ocr) -ne $pages) {
        throw "Os contadores de páginas processadas são divergentes."
    }
    return $true
}

function Assert-TcmBaExpensePublicationApproval {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Events,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactSha256
    )

    if ($ArtifactSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "A aprovação exige um SHA-256 hexadecimal."
    }
    $completedEvents = @(
        $Events | Where-Object {
            $_.event -eq "expense_publication_completed"
        }
    )
    if ($completedEvents.Count -ne 1) {
        throw "A aprovação exige um único evento final de despesa."
    }
    $event = $completedEvents[0]
    if (
        $event.artifact_sha256 -isnot [string] -or
        $event.artifact_sha256.ToLowerInvariant() -ne
            $ArtifactSha256.ToLowerInvariant()
    ) {
        throw "O publicador não atingiu o SHA-256 solicitado."
    }
    $artifacts = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.artifacts -FieldName "artifacts"
    $reportsPublished = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.reports_published -FieldName "reports_published"
    $publishedLines = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.published_lines -FieldName "published_lines"
    $alreadyPublished = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.already_published -FieldName "already_published"
    $needsReview = ConvertTo-TcmBaNonNegativeInteger `
        -Value $event.needs_review -FieldName "needs_review"
    $null = $publishedLines

    if (
        $artifacts -ne 1 -or
        $needsReview -ne 0 -or
        ($reportsPublished + $alreadyPublished) -ne 1
    ) {
        throw "A publicação exata não comprovou um relatório íntegro."
    }
    return $true
}

function Read-TcmBaCommitmentBudgetBenchmarkEvent {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Output
    )

    $events = @()
    foreach ($line in $Output) {
        $text = $line.ToString().Trim()
        if (-not $text.StartsWith("{")) {
            continue
        }
        try {
            $event = $text | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($event.event -eq "tcm_ba_commitment_budget_layout_benchmark") {
            $events += $event
        }
    }
    if ($events.Count -ne 1 -or $events[0].gate -ne "PASS") {
        throw "O benchmark de dotações não produziu um único gate aprovado."
    }
    return $events[0]
}

function Read-TcmBaCommitmentAmountBenchmarkEvent {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object[]]$Output
    )

    $events = @()
    foreach ($line in $Output) {
        $text = $line.ToString().Trim()
        if (-not $text.StartsWith("{")) {
            continue
        }
        try {
            $event = $text | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($event.event -eq "tcm_ba_commitment_amount_layout_benchmark") {
            $events += $event
        }
    }
    if ($events.Count -ne 1 -or $events[0].gate -ne "PASS") {
        throw "O benchmark de valores não produziu um único gate aprovado."
    }
    return $events[0]
}
