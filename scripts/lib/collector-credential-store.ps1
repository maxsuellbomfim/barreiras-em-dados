Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Security
$script:CollectorCredentialEntropy = [Text.Encoding]::UTF8.GetBytes(
    "Barreiras360:collector-credentials:v1"
)

function Convert-CollectorSecureStringToPlainText {
    param(
        [Parameter(Mandatory = $true)]
        [Security.SecureString]$Value
    )

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Protect-CollectorCredential {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $plainBytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $protectedBytes = $null
    try {
        $protectedBytes = [Security.Cryptography.ProtectedData]::Protect(
            $plainBytes,
            $script:CollectorCredentialEntropy,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        return [Convert]::ToBase64String($protectedBytes)
    }
    finally {
        if ($plainBytes) {
            [Array]::Clear($plainBytes, 0, $plainBytes.Length)
        }
        if ($protectedBytes) {
            [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
        }
    }
}

function Unprotect-CollectorCredential {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CipherText
    )

    $protectedBytes = $null
    $plainBytes = $null
    try {
        $protectedBytes = [Convert]::FromBase64String($CipherText)
        $plainBytes = [Security.Cryptography.ProtectedData]::Unprotect(
            $protectedBytes,
            $script:CollectorCredentialEntropy,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        return [Text.Encoding]::UTF8.GetString($plainBytes)
    }
    catch {
        throw (
            "O Windows não conseguiu descriptografar o cofre local para " +
            "este usuário."
        )
    }
    finally {
        if ($protectedBytes) {
            [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
        }
        if ($plainBytes) {
            [Array]::Clear($plainBytes, 0, $plainBytes.Length)
        }
    }
}

function Write-CollectorCredentialStore {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRef,
        [Parameter(Mandatory = $true)]
        [string]$DatabasePassword,
        [Parameter(Mandatory = $true)]
        [string]$WorkloadPassword,
        [ValidateSet("active", "staged")]
        [string]$Status = "active"
    )

    if ($env:OS -ne "Windows_NT") {
        throw "O cofre DPAPI local só pode ser criado no Windows."
    }
    if ($ProjectRef -notmatch '^[a-z0-9]{20}$') {
        throw "O identificador do projeto Supabase é inválido."
    }
    if ($DatabasePassword.Length -lt 24) {
        throw "A senha PostgreSQL deve ter ao menos 24 caracteres."
    }
    if ($WorkloadPassword.Length -lt 24) {
        throw "A senha do usuário técnico deve ter ao menos 24 caracteres."
    }

    $directory = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($directory)) {
        [IO.Directory]::CreateDirectory($directory) | Out-Null
    }
    $temporaryPath = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $payload = [ordered]@{
            version = 1
            protection_scope = "CurrentUser"
            project_ref = $ProjectRef
            status = $Status
            database_password_dpapi = Protect-CollectorCredential $DatabasePassword
            workload_password_dpapi = Protect-CollectorCredential $WorkloadPassword
            updated_at = [DateTimeOffset]::UtcNow.ToString("O")
        }
        $json = $payload | ConvertTo-Json -Depth 3
        [IO.File]::WriteAllText(
            $temporaryPath,
            $json,
            [Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
        $payload = $null
        $json = $null
    }
}

function Read-CollectorCredentialStore {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedProjectRef
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        $payload = Get-Content -Raw -LiteralPath $Path -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        throw "O cofre local do coletor está ilegível ou corrompido."
    }
    if ($payload.version -ne 1 -or $payload.protection_scope -ne "CurrentUser") {
        throw "O formato do cofre local do coletor não é suportado."
    }
    if ($payload.project_ref -ne $ExpectedProjectRef) {
        throw "O cofre local não pertence ao projeto Supabase esperado."
    }
    if ($payload.status -ne "active") {
        throw "O cofre local contém uma rotação incompleta e não pode ser usado."
    }

    $databasePassword = Unprotect-CollectorCredential (
        $payload.database_password_dpapi
    )
    $workloadPassword = Unprotect-CollectorCredential (
        $payload.workload_password_dpapi
    )
    if ($databasePassword.Length -lt 24 -or $workloadPassword.Length -lt 24) {
        throw "O cofre local contém uma credencial técnica inválida."
    }
    return [pscustomobject]@{
        DatabasePassword = $databasePassword
        WorkloadPassword = $workloadPassword
        Status = $payload.status
    }
}
