param(
    [string]$Competence = "01/2021",
    [ValidateRange(1, 5)]
    [int]$MaxDocuments = 1,
    [switch]$AutoCompetence,
    [switch]$PlanOnly,
    [switch]$ReportOnly,
    [switch]$AuditOnly,
    [switch]$CommitmentReplayOnly,
    [switch]$CommitmentBudgetBenchmarkOnly,
    [switch]$CommitmentAmountBenchmarkOnly,
    [switch]$CommitmentCreditorBenchmarkOnly,
    [switch]$CommitmentIssueDateBenchmarkOnly,
    [object]$RequestsPerMinute = 30,
    [string]$PythonPath = ""
)
$ErrorActionPreference = "Stop"
$projectRef = "mpladsyzilmgiefejpkq"
$collectorUser = "collector_querido_diario.$projectRef"
$projectRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
$credentialStorePath = Join-Path $projectRoot `
    ".collector-credentials.local.json"
$sslRootCertificatePath = $null
$credentialHelperPath = Join-Path $PSScriptRoot `
    "lib\collector-credential-store.ps1"
. $credentialHelperPath
$validationHelperPath = Join-Path $PSScriptRoot `
    "lib\tcm-ba-replay-validation.ps1"
. $validationHelperPath

$RequestsPerMinute = Assert-TcmBaRequestsPerMinute -RequestsPerMinute $RequestsPerMinute

function Read-LocalCollectorConfig {
    if (-not (Test-Path -LiteralPath $localConfigPath)) {
        throw (
            "Crie .env.collector.local com COLLECTOR_POOLER_HOST, " +
            "SUPABASE_PUBLISHABLE_KEY e SUPABASE_WORKLOAD_EMAIL."
        )
    }
    $lines = Get-Content -LiteralPath $localConfigPath -Encoding UTF8 |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            -not $_.TrimStart().StartsWith("#")
        }
    return ConvertFrom-StringData ($lines -join [Environment]::NewLine)
}

function Find-Python {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        return (Resolve-Path -LiteralPath $PythonPath).Path
    }
    $bundled = Join-Path $env:LOCALAPPDATA `
        "Python\pythoncore-3.14-64\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python não foi localizado."
}

function Read-AuditEvents {
    param([object[]]$Output)

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
        if ($event.event -eq "auditor_tcm_ba_document_batch_completed") {
            $events += $event
        }
    }
    if ($events.Count -eq 0) {
        throw "O auditor não produziu o evento documental final do TCM-BA."
    }
    return $events
}

function Read-CompletedEvents {
    param([object[]]$Output)

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
        if ($event.event -eq "collector_tcm_ba_documents_completed") {
            $events += $event
        }
    }
    if ($events.Count -eq 0) {
        throw "O coletor não produziu o evento documental final do TCM-BA."
    }
    return $events
}

function Read-TextEvents {
    param([object[]]$Output)

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
        if ($event.event -eq "tcm_ba_document_text_batch_completed") {
            $events += $event
        }
    }
    if ($events.Count -eq 0) {
        throw "O processador não produziu o evento final de texto TCM-BA."
    }
    return $events
}
function Read-CommitmentCandidateEvents {
    param([object[]]$Output)

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
        if ($event.event -eq "tcm_ba_commitment_candidate_batch_completed") {
            $events += $event
        }
    }
    if ($events.Count -ne 1) {
        throw "O processador não produziu um único evento final de empenhos."
    }
    return $events[0]
}
function Read-CommitmentCreditorBenchmarkEvent {
    param([object[]]$Output)

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
        if ($event.event -eq "tcm_ba_commitment_creditor_layout_benchmark") {
            $events += $event
        }
    }
    if ($events.Count -ne 1 -or $events[0].gate -ne "PASS") {
        throw "O benchmark de credores não produziu um único gate aprovado."
    }
    return $events[0]
}
function Read-CommitmentIssueDateBenchmarkEvent {
    param([object[]]$Output)

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
        if ($event.event -eq "tcm_ba_commitment_issue_date_layout_benchmark") {
            $events += $event
        }
    }
    if ($events.Count -ne 1 -or $events[0].gate -ne "PASS") {
        throw "O benchmark de datas não produziu um único gate aprovado."
    }
    return $events[0]
}
function Invoke-TcmBaDocumentProcessingReport {
    param(
        [string]$Python,
        [string]$ProjectRoot
    )

    Push-Location $ProjectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $reportOutput = @(
                & $Python -B -m barreiras_docproc.commands.report_tcm_ba_document_processing 2>&1
            )
            $reportExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $reportOutput | ForEach-Object { Write-Host $_ }
    if ($reportExitCode -ne 0) {
        throw "O relatório documental TCM-BA terminou com código $reportExitCode."
    }
}
function Invoke-TcmBaCommitmentCandidateProcessing {
    param(
        [string]$Python,
        [string]$ProjectRoot,
        [int]$Limit
    )

    Push-Location $ProjectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $candidateOutput = @(
                & $Python -B -m barreiras_docproc.commands.process_tcm_ba_commitments --limit $Limit 2>&1
            )
            $candidateExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $candidateOutput | ForEach-Object { Write-Host $_ }
    if ($candidateExitCode -ne 0) {
        throw "O processador de candidatos TCM-BA terminou com código $candidateExitCode."
    }
}
function Invoke-TcmBaCommitmentCandidateCoverage {
    param(
        [string]$Python,
        [string]$ProjectRoot
    )

    Push-Location $ProjectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $coverageOutput = @(
                & $Python -B -m barreiras_docproc.commands.report_tcm_ba_commitments 2>&1
            )
            $coverageExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $coverageOutput | ForEach-Object { Write-Host $_ }
    if ($coverageExitCode -ne 0) {
        throw "A cobertura dos candidatos de empenho TCM-BA foi bloqueada."
    }
}
function Invoke-TcmBaDocumentFamilyInventory {
    param(
        [string]$Python,
        [string]$ProjectRoot,
        [int]$Limit
    )

    Push-Location $ProjectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $familyOutput = @(
                & $Python -B -m barreiras_docproc.commands.process_tcm_ba_document_families --limit $Limit 2>&1
            )
            $familyExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $familyOutput | ForEach-Object { Write-Host $_ }
    if ($familyExitCode -ne 0) {
        throw "O inventário de famílias TCM-BA terminou com código $familyExitCode."
    }
}
function Invoke-TcmBaDocumentFamilyCoverage {
    param(
        [string]$Python,
        [string]$ProjectRoot
    )

    Push-Location $ProjectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $coverageOutput = @(
                & $Python -B -m barreiras_docproc.commands.report_tcm_ba_document_families 2>&1
            )
            $coverageExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $coverageOutput | ForEach-Object { Write-Host $_ }
    if ($coverageExitCode -ne 0) {
        throw "A cobertura das famílias TCM-BA foi bloqueada."
    }
}
function Invoke-TcmBaContractDocumentProcessing {
    param(
        [string]$Python,
        [string]$ProjectRoot,
        [ValidateRange(1, 50)]
        [int]$Limit
    )

    Push-Location $ProjectRoot
    try {
        & $Python -B -m barreiras_docproc.commands.process_tcm_ba_contract_documents --limit $Limit
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "A segmentação privada de contratos TCM-BA falhou."
    }
}
function Invoke-TcmBaContractDocumentCoverage {
    param(
        [string]$Python,
        [string]$ProjectRoot
    )

    Push-Location $ProjectRoot
    try {
        & $Python -B -m barreiras_docproc.commands.report_tcm_ba_contract_documents
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "A cobertura privada dos contratos TCM-BA foi bloqueada."
    }
}
function Invoke-TcmBaContractFieldProcessing {
    param(
        [string]$Python,
        [string]$ProjectRoot,
        [ValidateRange(1, 50)]
        [int]$Limit
    )

    Push-Location $ProjectRoot
    try {
        & $Python -B -m barreiras_docproc.commands.process_tcm_ba_contract_fields --limit $Limit
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "A extração privada dos campos contratuais TCM-BA falhou."
    }
}
function Invoke-TcmBaContractFieldCoverage {
    param(
        [string]$Python,
        [string]$ProjectRoot
    )

    Push-Location $ProjectRoot
    try {
        & $Python -B -m barreiras_docproc.commands.report_tcm_ba_contract_fields
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "A cobertura privada dos campos contratuais TCM-BA foi bloqueada."
    }
}
if ($AutoCompetence -and $PSBoundParameters.ContainsKey("Competence")) {
    throw "Não combine -AutoCompetence com -Competence."
}
if ($PlanOnly -and -not $AutoCompetence) {
    throw "-PlanOnly exige -AutoCompetence."
}
if ($ReportOnly -and ($AutoCompetence -or $PlanOnly)) {
    throw "-ReportOnly não pode ser combinado com -AutoCompetence ou -PlanOnly."
}
if (
    $AuditOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or
        $CommitmentReplayOnly -or $CommitmentBudgetBenchmarkOnly -or
        $CommitmentAmountBenchmarkOnly -or $CommitmentCreditorBenchmarkOnly -or
        $CommitmentIssueDateBenchmarkOnly)
) {
    throw "-AuditOnly não pode ser combinado com outro modo somente leitura."
}
if (
    $CommitmentReplayOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or $AuditOnly -or
        $CommitmentBudgetBenchmarkOnly -or $CommitmentCreditorBenchmarkOnly -or
        $CommitmentAmountBenchmarkOnly -or $CommitmentIssueDateBenchmarkOnly)
) {
    throw "-CommitmentReplayOnly não pode ser combinado com outro modo."
}
if (
    $CommitmentBudgetBenchmarkOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or $AuditOnly -or
        $CommitmentReplayOnly -or $CommitmentCreditorBenchmarkOnly -or
        $CommitmentAmountBenchmarkOnly -or $CommitmentIssueDateBenchmarkOnly)
) {
    throw "-CommitmentBudgetBenchmarkOnly não pode ser combinado com outro modo."
}
if (
    $CommitmentCreditorBenchmarkOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or $AuditOnly -or
        $CommitmentReplayOnly -or $CommitmentBudgetBenchmarkOnly -or
        $CommitmentAmountBenchmarkOnly -or $CommitmentIssueDateBenchmarkOnly)
) {
    throw "-CommitmentCreditorBenchmarkOnly não pode ser combinado com outro modo."
}
if (
    $CommitmentIssueDateBenchmarkOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or $AuditOnly -or
        $CommitmentReplayOnly -or $CommitmentBudgetBenchmarkOnly -or
        $CommitmentAmountBenchmarkOnly -or $CommitmentCreditorBenchmarkOnly)
) {
    throw "-CommitmentIssueDateBenchmarkOnly não pode ser combinado com outro modo."
}
if (
    $CommitmentAmountBenchmarkOnly -and
    ($AutoCompetence -or $PlanOnly -or $ReportOnly -or $AuditOnly -or
        $CommitmentReplayOnly -or $CommitmentBudgetBenchmarkOnly -or
        $CommitmentCreditorBenchmarkOnly -or $CommitmentIssueDateBenchmarkOnly)
) {
    throw "-CommitmentAmountBenchmarkOnly não pode ser combinado com outro modo."
}
if (
    -not $AutoCompetence -and
    $Competence -notmatch '^(0[1-9]|1[0-2])/\d{4}$'
) {
    throw "A competência deve usar o formato MM/AAAA."
}
Write-Host "Piloto local seguro dos documentos mensais do TCM-BA" -ForegroundColor Green
Write-Host "As senhas ficam protegidas pelo usuário atual do Windows."
$localConfig = Read-LocalCollectorConfig
$poolerHost = $localConfig.COLLECTOR_POOLER_HOST
$publishableKey = $localConfig.SUPABASE_PUBLISHABLE_KEY
$workloadEmail = $localConfig.SUPABASE_WORKLOAD_EMAIL
if (-not $poolerHost.EndsWith(".pooler.supabase.com")) {
    throw "COLLECTOR_POOLER_HOST não pertence ao pooler do Supabase."
}
if (
    -not $publishableKey.StartsWith("sb_publishable_") -or
    $publishableKey.Length -lt 24
) {
    throw "SUPABASE_PUBLISHABLE_KEY local é inválida."
}
if ($workloadEmail.Split("@").Count -ne 2) {
    throw "SUPABASE_WORKLOAD_EMAIL local é inválido."
}

$credentialStore = Read-CollectorCredentialStore `
    -Path $credentialStorePath `
    -ExpectedProjectRef $projectRef
if ($credentialStore) {
    Write-Host "Credenciais protegidas do Windows carregadas." `
        -ForegroundColor Cyan
    $databasePassword = $credentialStore.DatabasePassword
    $workloadPassword = $credentialStore.WorkloadPassword
}
else {
    $databasePassword = $localConfig.COLLECTOR_DATABASE_PASSWORD
    $workloadPassword = $localConfig.SUPABASE_WORKLOAD_PASSWORD
}
if ([string]::IsNullOrWhiteSpace($databasePassword)) {
    $databasePassword = Convert-CollectorSecureStringToPlainText (
        Read-Host "Senha PostgreSQL do coletor" -AsSecureString
    )
}
if ([string]::IsNullOrWhiteSpace($workloadPassword)) {
    $workloadPassword = Convert-CollectorSecureStringToPlainText (
        Read-Host "Senha do usuário técnico do Storage" -AsSecureString
    )
}

try {
    if ($databasePassword.Length -lt 24) {
        throw "A senha PostgreSQL deve ter ao menos 24 caracteres."
    }
    if ($workloadPassword.Length -lt 24) {
        throw "A senha do usuário técnico deve ter ao menos 24 caracteres."
    }
    $bundledCa = Join-Path $projectRoot `
        "config\certificates\supabase-prod-ca-2021.crt"
    if (-not (Test-Path -LiteralPath $bundledCa)) {
        throw "O certificado CA oficial do Supabase não foi localizado."
    }
    $sslRootCertificatePath = Join-Path ([IO.Path]::GetTempPath()) (
        "barreiras-" + [IO.Path]::GetRandomFileName() + ".crt"
    )
    Copy-Item -LiteralPath $bundledCa -Destination $sslRootCertificatePath

    $encodedDatabasePassword = [Uri]::EscapeDataString($databasePassword)
    $encodedCertificate = [Uri]::EscapeDataString($sslRootCertificatePath)
    $env:DATABASE_URL = (
        "postgresql://${collectorUser}:${encodedDatabasePassword}" +
        "@${poolerHost}:5432/postgres" +
        "?sslmode=verify-full&sslrootcert=${encodedCertificate}"
    )
    $env:APP_ENV = "development"
    $env:LOG_LEVEL = "INFO"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = (
        "workers/collectors/src;workers/document-processing/src"
    )
    $env:PERSISTENCE_MODE = "postgres-supabase"
    $env:SUPABASE_URL = "https://$projectRef.supabase.co"
    $env:SUPABASE_PUBLISHABLE_KEY = $publishableKey
    $env:SUPABASE_WORKLOAD_EMAIL = $workloadEmail
    $env:SUPABASE_WORKLOAD_PASSWORD = $workloadPassword
    $env:SUPABASE_RAW_ARTIFACTS_BUCKET = "raw-artifacts"

    $python = Find-Python
    if ($AuditOnly) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $auditOutput = @(
                    & $python -B -m barreiras_collectors.commands.audit_tcm_ba_document_batch --competence $Competence 2>&1
                )
                $auditExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $auditOutput | ForEach-Object { Write-Host $_ }
        if ($auditExitCode -ne 0) {
            throw "O auditor terminou com código $auditExitCode."
        }
        $auditEvents = @(Read-AuditEvents -Output $auditOutput)
        if (
            $auditEvents.Count -ne 1 -or
            $auditEvents[0].gate -ne "PASS" -or
            $auditEvents[0].competence -ne $Competence
        ) {
            throw "A auditoria não aprovou uma competência única e exata."
        }
        Write-Host "TCM_BA_DOCUMENT_AUDIT_ONLY" -ForegroundColor Cyan
        return
    }
    if ($ReportOnly) {
        Invoke-TcmBaDocumentProcessingReport -Python $python -ProjectRoot $projectRoot
        Invoke-TcmBaDocumentFamilyCoverage -Python $python -ProjectRoot $projectRoot
        Invoke-TcmBaContractDocumentCoverage -Python $python -ProjectRoot $projectRoot
        Invoke-TcmBaContractFieldCoverage -Python $python -ProjectRoot $projectRoot
        Invoke-TcmBaCommitmentCandidateCoverage -Python $python -ProjectRoot $projectRoot
        Write-Host "TCM_BA_DOCUMENT_REPORT_ONLY" -ForegroundColor Cyan
        return
    }
    if ($CommitmentBudgetBenchmarkOnly) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $benchmarkOutput = @(
                    & $python -B -m barreiras_docproc.commands.benchmark_tcm_ba_commitment_budgets --limit 500 2>&1
                )
                $benchmarkExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $benchmarkOutput | ForEach-Object { Write-Host $_ }
        if ($benchmarkExitCode -ne 0) {
            throw "O benchmark privado das dotações TCM-BA foi bloqueado."
        }
        Read-TcmBaCommitmentBudgetBenchmarkEvent `
            -Output $benchmarkOutput | Out-Null
        Write-Host "TCM_BA_COMMITMENT_BUDGET_BENCHMARK_APPROVED" `
            -ForegroundColor Cyan
        return
    }
    if ($CommitmentAmountBenchmarkOnly) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $benchmarkOutput = @(
                    & $python -B -m barreiras_docproc.commands.benchmark_tcm_ba_commitment_amounts --limit 500 2>&1
                )
                $benchmarkExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $benchmarkOutput | ForEach-Object { Write-Host $_ }
        if ($benchmarkExitCode -ne 0) {
            throw "O benchmark privado dos valores TCM-BA foi bloqueado."
        }
        Read-TcmBaCommitmentAmountBenchmarkEvent `
            -Output $benchmarkOutput | Out-Null
        Write-Host "TCM_BA_COMMITMENT_AMOUNT_BENCHMARK_APPROVED" `
            -ForegroundColor Cyan
        return
    }
    if ($CommitmentCreditorBenchmarkOnly) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $benchmarkOutput = @(
                    & $python -B -m barreiras_docproc.commands.benchmark_tcm_ba_commitment_creditors --limit 500 2>&1
                )
                $benchmarkExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $benchmarkOutput | ForEach-Object { Write-Host $_ }
        if ($benchmarkExitCode -ne 0) {
            throw "O benchmark privado dos credores TCM-BA foi bloqueado."
        }
        Read-CommitmentCreditorBenchmarkEvent -Output $benchmarkOutput | Out-Null
        Write-Host "TCM_BA_COMMITMENT_CREDITOR_BENCHMARK_APPROVED" -ForegroundColor Cyan
        return
    }
    if ($CommitmentIssueDateBenchmarkOnly) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $benchmarkOutput = @(
                    & $python -B -m barreiras_docproc.commands.benchmark_tcm_ba_commitment_dates --limit 500 2>&1
                )
                $benchmarkExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $benchmarkOutput | ForEach-Object { Write-Host $_ }
        if ($benchmarkExitCode -ne 0) {
            throw "O benchmark privado das datas TCM-BA foi bloqueado."
        }
        Read-CommitmentIssueDateBenchmarkEvent -Output $benchmarkOutput | Out-Null
        Write-Host "TCM_BA_COMMITMENT_ISSUE_DATE_BENCHMARK_APPROVED" -ForegroundColor Cyan
        return
    }
    if ($CommitmentReplayOnly) {
        $drained = $false
        for ($batch = 1; $batch -le 20; $batch++) {
            Push-Location $projectRoot
            try {
                $previousErrorActionPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = "Continue"
                    $candidateOutput = @(
                        & $python -B -m barreiras_docproc.commands.process_tcm_ba_commitments --limit 50 2>&1
                    )
                    $candidateExitCode = $LASTEXITCODE
                }
                finally {
                    $ErrorActionPreference = $previousErrorActionPreference
                }
            }
            finally {
                Pop-Location
            }
            $candidateOutput | ForEach-Object { Write-Host $_ }
            if ($candidateExitCode -ne 0) {
                throw "O replay privado de empenhos falhou no lote $batch."
            }
            $event = Read-CommitmentCandidateEvents -Output $candidateOutput
            if ($event.pending_found -eq 0) {
                $drained = $true
                break
            }
        }
        if (-not $drained) {
            throw "O replay privado excedeu o limite de 1.000 artefatos."
        }
        Invoke-TcmBaCommitmentCandidateCoverage -Python $python -ProjectRoot $projectRoot
        Write-Host "TCM_BA_COMMITMENT_REPLAY_APPROVED" -ForegroundColor Cyan
        return
    }
    if ($AutoCompetence) {
        Push-Location $projectRoot
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $planOutput = @(
                    & $python -B -m barreiras_collectors.commands.plan_tcm_ba_document_batch --year-from 2021 --report 2>&1
                )
                $planExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
        $planOutput | ForEach-Object { Write-Host $_ }
        if ($planExitCode -ne 0) {
            throw "O planejador terminou com código $planExitCode."
        }
        $planEvents = @()
        foreach ($line in $planOutput) {
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
            if ($event.event -eq "tcm_ba_document_plan") {
                $planEvents += $event
            }
        }
        if ($planEvents.Count -ne 1) {
            throw "O planejador não retornou um evento de cobertura único."
        }
        $plannedCompetences = @(
            $planOutput |
                ForEach-Object { $_.ToString().Trim() } |
                Where-Object { $_ -match '^(0[1-9]|1[0-2])/\d{4}$' }
        )
        if ($plannedCompetences.Count -eq 0) {
            if ($planEvents[0].coverage_status -eq "blocked") {
                Write-Host "TCM_BA_DOCUMENT_BACKLOG_BLOCKED" -ForegroundColor Yellow
                return
            }
            if ($planEvents[0].coverage_status -ne "complete") {
                throw "O estado sem competência do planejador é inválido."
            }
            Write-Host "TCM_BA_DOCUMENT_NO_ELIGIBLE_COMPETENCE" -ForegroundColor Cyan
            return
        }
        if (
            $plannedCompetences.Count -ne 1 -or
            $planEvents[0].coverage_status -ne "partial"
        ) {
            throw "O planejador não retornou uma competência parcial única."
        }
        $Competence = $plannedCompetences[0]
        Write-Host "Competência planejada: $Competence" -ForegroundColor Cyan
        if ($PlanOnly) {
            Write-Host "TCM_BA_DOCUMENT_PLAN_ONLY" -ForegroundColor Cyan
            return
        }
    }
    Push-Location $projectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $output = @(
                & $python -B -m barreiras_collectors.commands.collect_tcm_ba_documents --competence $Competence --max-documents $MaxDocuments --requests-per-minute $RequestsPerMinute 2>&1
            )
            $nativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($nativeExitCode -ne 0) {
        throw "O coletor terminou com código $nativeExitCode."
    }
    $events = @(Read-CompletedEvents -Output $output)
    $null = Assert-TcmBaDocumentBatchApproval -Events $events -ExpectedCompetence $Competence -MaxDocuments $MaxDocuments
    $collectorEvent = $events[0]

    Push-Location $projectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $auditOutput = @(
                & $python -B -m barreiras_collectors.commands.audit_tcm_ba_document_batch --competence $Competence 2>&1
            )
            $auditExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $auditOutput | ForEach-Object { Write-Host $_ }
    if ($auditExitCode -ne 0) {
        throw "O auditor terminou com código $auditExitCode."
    }
    $auditEvents = @(Read-AuditEvents -Output $auditOutput)
    $null = Assert-TcmBaDocumentAuditApproval `
        -CollectorEvent $collectorEvent `
        -AuditEvents $auditEvents
    Push-Location $projectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $textOutput = @(
                & $python -B -m barreiras_docproc.commands.process_tcm_ba_documents --limit $MaxDocuments 2>&1
            )
            $textExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $textOutput | ForEach-Object { Write-Host $_ }
    if ($textExitCode -ne 0) {
        throw "O processador de texto terminou com código $textExitCode."
    }
    $textEvents = @(Read-TextEvents -Output $textOutput)
    $null = Assert-TcmBaDocumentTextApproval `
        -Events $textEvents `
        -MaxDocuments $MaxDocuments
    Push-Location $projectRoot
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $ocrOutput = @(
                & $python -B -m barreiras_docproc.commands.ocr_gazette_pages --source tcm-ba --limit-pages 30 2>&1
            )
            $ocrExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }
    $ocrOutput | ForEach-Object { Write-Host $_ }
    if ($ocrExitCode -ne 0) {
        throw "O OCR TCM-BA terminou com código $ocrExitCode."
    }
    Invoke-TcmBaDocumentProcessingReport -Python $python -ProjectRoot $projectRoot
    $familyCatchUpLimit = Get-TcmBaDocumentFamilyCatchUpLimit `
        -MaxDocuments $MaxDocuments
    Invoke-TcmBaDocumentFamilyInventory `
        -Python $python `
        -ProjectRoot $projectRoot `
        -Limit $familyCatchUpLimit
    Invoke-TcmBaDocumentFamilyCoverage `
        -Python $python `
        -ProjectRoot $projectRoot
    Invoke-TcmBaContractDocumentProcessing -Python $python -ProjectRoot $projectRoot -Limit $MaxDocuments
    Invoke-TcmBaContractDocumentCoverage -Python $python -ProjectRoot $projectRoot
    Invoke-TcmBaContractFieldProcessing -Python $python -ProjectRoot $projectRoot -Limit $MaxDocuments
    Invoke-TcmBaContractFieldCoverage -Python $python -ProjectRoot $projectRoot
    Invoke-TcmBaCommitmentCandidateProcessing `
        -Python $python `
        -ProjectRoot $projectRoot `
        -Limit $MaxDocuments
    Invoke-TcmBaCommitmentCandidateCoverage `
        -Python $python `
        -ProjectRoot $projectRoot
    Write-Host "TCM_BA_DOCUMENT_PILOT_APPROVED" -ForegroundColor Green
}
finally {
    foreach ($name in @(
        "DATABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_WORKLOAD_EMAIL",
        "SUPABASE_WORKLOAD_PASSWORD"
    )) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    if (
        -not [string]::IsNullOrWhiteSpace($sslRootCertificatePath) -and
        (Test-Path -LiteralPath $sslRootCertificatePath)
    ) {
        Remove-Item -LiteralPath $sslRootCertificatePath -Force
    }
    $databasePassword = $null
    $workloadPassword = $null
    $credentialStore = $null
    $encodedDatabasePassword = $null
    $env:DATABASE_URL = $null
}
