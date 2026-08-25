param(
    [switch]$DescribePlan,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRef = "mpladsyzilmgiefejpkq"
$databaseRole = "collector_querido_diario"
$databaseUser = "$databaseRole.$projectRef"
$storageUserId = "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a"
$repository = "maxsuellbomfim/barreiras-em-dados"
$githubSecretNames = @(
    "QUERIDO_DIARIO_DATABASE_URL",
    "MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD"
)

if ($DescribePlan) {
    [ordered]@{
        project_ref = $projectRef
        database_role = $databaseRole
        storage_user_id = $storageUserId
        github_secrets = $githubSecretNames
        local_protection = "Windows DPAPI CurrentUser"
        plaintext_persisted = $false
    } | ConvertTo-Json -Depth 3
    exit 0
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $projectRoot ".env.collector.local"
$credentialStorePath = Join-Path $projectRoot `
    ".collector-credentials.local.json"
$credentialHelperPath = Join-Path $PSScriptRoot `
    "lib\collector-credential-store.ps1"
$supabaseCommand = Join-Path $projectRoot `
    "node_modules\.bin\supabase.cmd"
$temporarySqlPath = $null
$temporaryCaPath = $null
$databasePassword = $null
$workloadPassword = $null
$serviceRoleKey = $null
$workloadEmail = $null
$databaseUrl = $null

. $credentialHelperPath

function Read-LocalCollectorConfig {
    if (-not (Test-Path -LiteralPath $localConfigPath)) {
        throw (
            "O arquivo .env.collector.local não foi localizado. " +
            "Ele deve conter apenas host, chave publicável e e-mail técnico."
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
    throw "Python não foi localizado para validar o PostgreSQL."
}

function New-CollectorPassword {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        $encoded = ([Convert]::ToBase64String($bytes)).TrimEnd('=')
        return $encoded.Replace('+', '-').Replace('/', '_')
    }
    finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Invoke-GitHubSecretSet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        $installed = "C:\Program Files\GitHub CLI\gh.exe"
        if (Test-Path -LiteralPath $installed) {
            $gh = [pscustomobject]@{ Source = $installed }
        }
        else {
            throw "GitHub CLI não foi localizado."
        }
    }
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $gh.Source
    $startInfo.Arguments = (
        'secret set "' + $Name + '" --repo "' + $repository + '"'
    )
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "O GitHub CLI não iniciou."
        }
        $process.StandardInput.Write($Value)
        $process.StandardInput.Close()
        $null = $process.StandardOutput.ReadToEnd()
        $null = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Não foi possível atualizar o secret GitHub $Name."
        }
    }
    finally {
        $process.Dispose()
    }
}

function Set-LocalWorkloadEmail {
    param([Parameter(Mandatory = $true)][string]$Email)

    $content = [IO.File]::ReadAllText($localConfigPath)
    if ($content -match '(?m)^SUPABASE_WORKLOAD_EMAIL=') {
        $content = [regex]::Replace(
            $content,
            '(?m)^SUPABASE_WORKLOAD_EMAIL=.*$',
            "SUPABASE_WORKLOAD_EMAIL=$Email"
        )
    }
    else {
        $content = $content.TrimEnd() + [Environment]::NewLine +
            "SUPABASE_WORKLOAD_EMAIL=$Email" + [Environment]::NewLine
    }
    [IO.File]::WriteAllText(
        $localConfigPath,
        $content,
        [Text.UTF8Encoding]::new($false)
    )
}

function Get-ServiceRoleKey {
    if (-not (Test-Path -LiteralPath $supabaseCommand)) {
        throw "Supabase CLI local não foi localizado. Execute pnpm install."
    }
    $raw = @(
        & $supabaseCommand projects api-keys `
            --project-ref $projectRef --reveal --output json 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Não foi possível consultar as chaves do projeto Supabase."
    }
    try {
        $keys = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
    }
    catch {
        throw "A resposta das chaves do Supabase não pôde ser validada."
    }
    $serviceRole = @($keys) | Where-Object {
        $_.name -eq "service_role" -or
        $_.type -eq "service_role" -or
        $_.id -eq "service_role"
    } | Select-Object -First 1
    if (-not $serviceRole) {
        throw "A chave service_role legada não foi localizada."
    }
    foreach ($property in @("api_key", "value", "key")) {
        $candidate = $serviceRole.$property
        if (
            -not [string]::IsNullOrWhiteSpace($candidate) -and
            $candidate.StartsWith("eyJ")
        ) {
            return $candidate
        }
    }
    throw "A chave service_role retornada não tem formato reconhecido."
}

function Get-StorageUser {
    param([Parameter(Mandatory = $true)][string]$ServiceRoleKey)

    $headers = @{
        apikey = $ServiceRoleKey
        Authorization = "Bearer $ServiceRoleKey"
    }
    try {
        $user = Invoke-RestMethod -Method Get -Headers $headers -Uri (
            "https://$projectRef.supabase.co/auth/v1/admin/users/" +
            $storageUserId
        )
    }
    catch {
        throw "Não foi possível validar o usuário técnico no Supabase Auth."
    }
    if ($user.id -ne $storageUserId -or $user.email -notmatch '@') {
        throw "O usuário técnico retornado pelo Supabase é incompatível."
    }
    return $user
}

function Set-StorageUserPassword {
    param(
        [Parameter(Mandatory = $true)][string]$ServiceRoleKey,
        [Parameter(Mandatory = $true)][string]$Password
    )

    $headers = @{
        apikey = $ServiceRoleKey
        Authorization = "Bearer $ServiceRoleKey"
        "Content-Type" = "application/json"
    }
    $body = @{ password = $Password } | ConvertTo-Json -Compress
    try {
        $user = Invoke-RestMethod -Method Put -Headers $headers -Body $body `
            -Uri (
                "https://$projectRef.supabase.co/auth/v1/admin/users/" +
                $storageUserId
            )
    }
    catch {
        throw "Não foi possível rotacionar a senha do usuário técnico."
    }
    if ($user.id -ne $storageUserId) {
        throw "O Supabase não confirmou o usuário técnico rotacionado."
    }
}

function Test-StorageUserPassword {
    param(
        [Parameter(Mandatory = $true)][string]$PublishableKey,
        [Parameter(Mandatory = $true)][string]$Email,
        [Parameter(Mandatory = $true)][string]$Password
    )

    $headers = @{
        apikey = $PublishableKey
        "Content-Type" = "application/json"
    }
    $body = @{ email = $Email; password = $Password } |
        ConvertTo-Json -Compress
    try {
        $session = Invoke-RestMethod -Method Post -Headers $headers `
            -Body $body -Uri (
                "https://$projectRef.supabase.co/auth/v1/token" +
                "?grant_type=password"
            )
    }
    catch {
        throw "A nova senha do usuário técnico não passou na autenticação."
    }
    if ([string]::IsNullOrWhiteSpace($session.access_token)) {
        throw "O Supabase não retornou uma sessão para o usuário técnico."
    }
    $session = $null
}

function Set-DatabaseRolePassword {
    param([Parameter(Mandatory = $true)][string]$Password)

    $escapedPassword = $Password.Replace("'", "''")
    $temporarySqlPath = Join-Path ([IO.Path]::GetTempPath()) (
        "barreiras-credential-rotation-" +
        [Guid]::NewGuid().ToString("N") + ".sql"
    )
    $sql = @"
alter role $databaseRole password '$escapedPassword';
insert into audit.audit_events (
    actor_type,
    actor_subject,
    action,
    target_type,
    target_id,
    after_state,
    metadata
) values (
    'administrator',
    'authorized-local-rotation',
    'collector_credentials.rotated',
    'collector_workload',
    '$databaseRole',
    jsonb_build_object(
        'database_role', '$databaseRole',
        'storage_auth_user_id', '$storageUserId'
    ),
    jsonb_build_object(
        'secret_values_persisted', false,
        'storage_scope', 'windows-dpapi-current-user'
    )
);
"@
    try {
        [IO.File]::WriteAllText(
            $temporarySqlPath,
            $sql,
            [Text.UTF8Encoding]::new($false)
        )
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $null = @(
                & $supabaseCommand db query --linked `
                    --file $temporarySqlPath 2>&1
            )
            $nativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($nativeExitCode -ne 0) {
            throw "A rotação da senha PostgreSQL não foi confirmada."
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporarySqlPath) {
            Remove-Item -LiteralPath $temporarySqlPath -Force
        }
        $sql = $null
        $escapedPassword = $null
    }
}

function Test-DatabaseRolePassword {
    param(
        [Parameter(Mandatory = $true)][string]$PoolerHost,
        [Parameter(Mandatory = $true)][string]$Password
    )

    $bundledCa = Join-Path $projectRoot `
        "config\certificates\supabase-prod-ca-2021.crt"
    if (-not (Test-Path -LiteralPath $bundledCa)) {
        throw "O certificado CA oficial do Supabase não foi localizado."
    }
    $temporaryCaPath = Join-Path ([IO.Path]::GetTempPath()) (
        "barreiras-" + [IO.Path]::GetRandomFileName() + ".crt"
    )
    Copy-Item -LiteralPath $bundledCa -Destination $temporaryCaPath
    try {
        $env:COLLECTOR_ROTATION_DATABASE_URL = (
            "postgresql://${databaseUser}:" +
            ([Uri]::EscapeDataString($Password)) +
            "@${PoolerHost}:5432/postgres?sslmode=verify-full&sslrootcert=" +
            ([Uri]::EscapeDataString($temporaryCaPath))
        )
        $python = Find-Python
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $probe = @(
                & $python -B -c (
                    "import os, psycopg; " +
                    "c=psycopg.connect(os.environ['COLLECTOR_ROTATION_DATABASE_URL']); " +
                    "c.execute('select 1').fetchone(); c.close(); " +
                    "print('DATABASE_LOGIN_OK')"
                ) 2>&1
            )
            $nativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if (
            $nativeExitCode -ne 0 -or
            ($probe -join "`n") -notmatch 'DATABASE_LOGIN_OK'
        ) {
            throw "A nova senha PostgreSQL não passou no teste de conexão."
        }
    }
    finally {
        Remove-Item Env:COLLECTOR_ROTATION_DATABASE_URL `
            -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $temporaryCaPath) {
            Remove-Item -LiteralPath $temporaryCaPath -Force
        }
    }
}

try {
    Write-Host "Rotação restrita das credenciais técnicas do coletor" `
        -ForegroundColor Green

    $localConfig = Read-LocalCollectorConfig
    $poolerHost = $localConfig.COLLECTOR_POOLER_HOST
    $publishableKey = $localConfig.SUPABASE_PUBLISHABLE_KEY
    if (
        [string]::IsNullOrWhiteSpace($poolerHost) -or
        -not $poolerHost.EndsWith(".pooler.supabase.com")
    ) {
        throw "COLLECTOR_POOLER_HOST não pertence ao pooler do Supabase."
    }
    if (
        [string]::IsNullOrWhiteSpace($publishableKey) -or
        -not $publishableKey.StartsWith("sb_publishable_") -or
        $publishableKey.Length -lt 24
    ) {
        throw "SUPABASE_PUBLISHABLE_KEY local é inválida."
    }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh -and -not (Test-Path "C:\Program Files\GitHub CLI\gh.exe")) {
        throw "GitHub CLI não foi localizado."
    }
    $ghPath = if ($gh) { $gh.Source } else {
        "C:\Program Files\GitHub CLI\gh.exe"
    }
    $null = & $ghPath auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "O GitHub CLI não está autenticado."
    }

    Write-Host "1/7 Preflight do Supabase e GitHub concluído."
    $serviceRoleKey = Get-ServiceRoleKey
    $storageUser = Get-StorageUser -ServiceRoleKey $serviceRoleKey
    $workloadEmail = $storageUser.email
    $databasePassword = New-CollectorPassword
    $workloadPassword = New-CollectorPassword

    Write-CollectorCredentialStore -Path $credentialStorePath `
        -ProjectRef $projectRef `
        -DatabasePassword $databasePassword `
        -WorkloadPassword $workloadPassword `
        -Status staged
    Write-Host "2/7 Novas credenciais protegidas pelo Windows (staged)."

    Set-StorageUserPassword -ServiceRoleKey $serviceRoleKey `
        -Password $workloadPassword
    Test-StorageUserPassword -PublishableKey $publishableKey `
        -Email $workloadEmail -Password $workloadPassword
    Write-Host "3/7 Usuário técnico do Storage rotacionado e validado."

    Invoke-GitHubSecretSet `
        -Name "MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD" `
        -Value $workloadPassword
    Write-Host "4/7 Secret municipal do GitHub atualizado."

    Set-DatabaseRolePassword -Password $databasePassword
    Test-DatabaseRolePassword -PoolerHost $poolerHost `
        -Password $databasePassword
    Write-Host "5/7 Role PostgreSQL rotacionada e validada."

    $repositoryCa = "config/certificates/supabase-prod-ca-2021.crt"
    $databaseUrl = (
        "postgresql://${databaseUser}:" +
        ([Uri]::EscapeDataString($databasePassword)) +
        "@${poolerHost}:5432/postgres" +
        "?sslmode=verify-full&sslrootcert=${repositoryCa}"
    )
    Invoke-GitHubSecretSet -Name "QUERIDO_DIARIO_DATABASE_URL" `
        -Value $databaseUrl
    Write-Host "6/7 Secret PostgreSQL compartilhado do GitHub atualizado."

    Set-LocalWorkloadEmail -Email $workloadEmail
    Write-CollectorCredentialStore -Path $credentialStorePath `
        -ProjectRef $projectRef `
        -DatabasePassword $databasePassword `
        -WorkloadPassword $workloadPassword `
        -Status active
    Write-Host "7/7 Cofre DPAPI local ativado."
    Write-Host "COLLECTOR_CREDENTIAL_ROTATION_APPROVED" `
        -ForegroundColor Green
}
catch {
    Write-Error (
        "A rotação não foi concluída. O cofre local protegido preserva " +
        "o estado staged para recuperação segura. Detalhe: " +
        $_.Exception.Message
    )
    exit 1
}
finally {
    Remove-Item Env:COLLECTOR_ROTATION_DATABASE_URL `
        -ErrorAction SilentlyContinue
    $databasePassword = $null
    $workloadPassword = $null
    $serviceRoleKey = $null
    $workloadEmail = $null
    $databaseUrl = $null
    $localConfig = $null
    $storageUser = $null
}
