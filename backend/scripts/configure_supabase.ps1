param(
    [string]$HostName = "aws-0-ap-southeast-1.pooler.supabase.com",
    [string]$UserName = "postgres.fyebyevqueurgubyiyir",
    [int]$Port = 5432,
    [string]$DatabaseName = "postgres",
    [switch]$ReuseExistingPassword
)

$ErrorActionPreference = "Stop"
$backendDirectory = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $backendDirectory ".env"
$passwordPointer = [IntPtr]::Zero
$password = $null

if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "backend/.env was not found. Create it from backend/.env.example first."
}
if ($HostName -match '(?i)YOUR-|PLACEHOLDER|EXAMPLE') {
    throw "Replace the example pooler hostname with the exact Session pooler host from Supabase Connect."
}
if ($UserName -match '(?i)YOUR-|PLACEHOLDER|EXAMPLE') {
    throw "Replace the example database username with the exact user from Supabase Connect."
}

try {
    [Net.Dns]::GetHostAddresses($HostName) | Out-Null
} catch {
    throw "The database host '$HostName' does not resolve. Check the Session pooler value in Supabase Connect."
}

$lines = [Collections.Generic.List[string]](Get-Content -LiteralPath $environmentFile)
$databaseLine = -1
for ($index = 0; $index -lt $lines.Count; $index++) {
    if ($lines[$index] -match '^DATABASE_URL=') {
        $databaseLine = $index
        break
    }
}

try {
    if ($ReuseExistingPassword) {
        if ($databaseLine -lt 0) {
            throw "DATABASE_URL is missing, so there is no saved password to reuse."
        }
        $existingUrl = $lines[$databaseLine].Substring("DATABASE_URL=".Length)
        $match = [regex]::Match($existingUrl, '^postgresql(?:\+psycopg2)?://[^:]+:(?<password>[^@]+)@')
        if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups["password"].Value)) {
            throw "The existing database password could not be read safely. Run the script without -ReuseExistingPassword."
        }
        $encodedPassword = $match.Groups["password"].Value
    } else {
        $securePassword = Read-Host "Supabase database password" -AsSecureString
        $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
        if ([string]::IsNullOrWhiteSpace($password)) {
            throw "The database password cannot be empty."
        }
        $encodedPassword = [Uri]::EscapeDataString($password)
    }

    $encodedUser = [Uri]::EscapeDataString($UserName)
    $encodedDatabase = [Uri]::EscapeDataString($DatabaseName)
    $databaseUrl = "postgresql+psycopg2://${encodedUser}:${encodedPassword}@${HostName}:${Port}/${encodedDatabase}?sslmode=require"

    if ($databaseLine -ge 0) {
        $lines[$databaseLine] = "DATABASE_URL=$databaseUrl"
    } else {
        $lines.Insert(0, "DATABASE_URL=$databaseUrl")
    }

    $defaults = @{
        DATABASE_POOL_SIZE = "5"
        DATABASE_MAX_OVERFLOW = "5"
        DATABASE_POOL_TIMEOUT_SECONDS = "10"
        DATABASE_POOL_RECYCLE_SECONDS = "300"
        DATABASE_CONNECT_TIMEOUT_SECONDS = "10"
        DATABASE_APPLICATION_NAME = "edvatiq_api"
    }
    foreach ($entry in $defaults.GetEnumerator()) {
        if (-not ($lines -match "^$($entry.Key)=")) {
            $lines.Add("$($entry.Key)=$($entry.Value)")
        }
    }

    [IO.File]::WriteAllLines($environmentFile, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "Supabase database configuration saved for $HostName without displaying the password."
    Write-Host "Run: python -m alembic upgrade head"
} finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    Remove-Variable password -ErrorAction SilentlyContinue
}
