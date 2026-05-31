#requires -RunAsAdministrator
<#
    Section Edge Proxy — Windows trust-store install.

    Usage:
        powershell -ExecutionPolicy Bypass -File windows.ps1 <cert.crt> [--uninstall]

    Adds (or removes) the supplied root certificate to the LocalMachine
    "Root" store using `certutil`. Requires administrator privileges —
    HKLM:\SOFTWARE\Microsoft\SystemCertificates\Root is admin-only.

    Exit codes:
        0  success
        1  invalid arguments
        2  certutil failed
        3  not running as administrator
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$CertPath,

    [Parameter(Position = 1)]
    [string]$Mode = "install"
)

if (-not (Test-Path $CertPath)) {
    Write-Host "ERROR: Cert file not found: $CertPath"
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator."
    exit 3
}

if ($Mode -eq "--uninstall") {
    # Find the cert by subject CN to obtain its thumbprint.
    Write-Host "Removing Section CA from LocalMachine\Root..."
    $existing = Get-ChildItem -Path Cert:\LocalMachine\Root |
        Where-Object { $_.Subject -like "*Section Edge Proxy Local CA*" }
    if ($null -eq $existing) {
        Write-Host "  (no matching cert found; nothing to do)"
        exit 0
    }
    foreach ($cert in $existing) {
        $tp = $cert.Thumbprint
        Write-Host "  removing $tp"
        & certutil.exe -delstore Root $tp | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: certutil -delstore failed (exit $LASTEXITCODE)"
            exit 2
        }
    }
    Write-Host "OK: Section CA removed from trust store."
    exit 0
}

Write-Host "Installing Section CA into LocalMachine\Root..."
& certutil.exe -addstore -f Root $CertPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: certutil -addstore failed (exit $LASTEXITCODE)"
    exit 2
}
Write-Host "OK: Section CA installed."
exit 0
