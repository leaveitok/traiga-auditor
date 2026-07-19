<#
.SYNOPSIS
    Exports the third-party applications your users have consented to in Microsoft Entra ID,
    so they can be reviewed for shadow AI. READ-ONLY.

.DESCRIPTION
    This script READS two things and writes a JSON file to YOUR disk. It does not modify
    anything in your tenant, it does not transmit anything anywhere, and it creates no app
    registration, client secret, or standing grant of any kind.

      1. Enterprise applications (service principals) - the app names/publishers.
      2. Delegated permission grants (oauth2PermissionGrants) - which app a user consented
         to, and what that consent lets the app reach.

    You authenticate as YOURSELF via an interactive sign-in. The access token lives only for
    this PowerShell session and disappears when you close it. There is nothing to revoke
    afterwards.

    PRIVACY: by default the output contains a COUNT of how many users consented to each app,
    never the user identities. Use -IncludeUsers only if you specifically want the names in
    order to go revoke them.

.PARAMETER OutFile
    Where to write the JSON. Default: .\oauth-grants-<tenant>-<date>.json

.PARAMETER IncludeUsers
    Include the UPNs of consenting users. OFF by default. This turns the export into
    employee-identifiable data - handle accordingly.

.EXAMPLE
    .\Export-EntraOAuthGrants.ps1
    .\Export-EntraOAuthGrants.ps1 -IncludeUsers -OutFile C:\temp\grants.json

.NOTES
    Requires Microsoft's own Microsoft.Graph PowerShell module (Microsoft-published):
        Install-Module Microsoft.Graph -Scope CurrentUser
    Requires a role that can read directory objects (e.g. Global Reader - a READ-ONLY role).
    This script is NOT Authenticode-signed. Verify it against the published SHA-256 checksum
    and read it before running - it is plain text on purpose.
#>
[CmdletBinding()]
param(
    [string] $OutFile,
    [switch] $IncludeUsers
)

$ErrorActionPreference = 'Stop'

# --- Read-only scopes. Nothing here can write to your tenant. -------------------
# Application.Read.All  : read service principals (app names, publishers)
# Directory.Read.All    : read the delegated permission grants
# The WRITE equivalents (*.ReadWrite.All) are deliberately NOT requested, so Entra
# itself will reject any write attempt regardless of what this script does.
$Scopes = @('Application.Read.All', 'Directory.Read.All')

Write-Host ''
Write-Host 'TRAIGA Auditor - Entra OAuth grant export (READ-ONLY)' -ForegroundColor Cyan
Write-Host '-----------------------------------------------------'
Write-Host 'This will sign you in interactively and READ app consent data.'
Write-Host 'It creates no app registration, no secret, and writes nothing to your tenant.'
Write-Host ''

if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Authentication)) {
    throw "Microsoft.Graph module not found. Install it first:  Install-Module Microsoft.Graph -Scope CurrentUser"
}

Connect-MgGraph -Scopes $Scopes -NoWelcome
$ctx = Get-MgContext
if (-not $ctx) { throw 'Sign-in failed.' }
Write-Host ("Signed in to tenant {0} as {1}" -f $ctx.TenantId, $ctx.Account) -ForegroundColor Green

# --- Read service principals (id -> app metadata) --------------------------------
Write-Host 'Reading enterprise applications...'
$spById = @{}
Get-MgServicePrincipal -All -Property 'id,appId,displayName,publisherName,signInAudience' |
    ForEach-Object { $spById[$_.Id] = $_ }
Write-Host ("  {0} applications" -f $spById.Count)

# --- Read delegated permission grants (the user-consent signal) -------------------
Write-Host 'Reading delegated permission grants (user consents)...'
$grants = Get-MgOauth2PermissionGrant -All
Write-Host ("  {0} grants" -f ($grants | Measure-Object).Count)

# --- Aggregate per application ----------------------------------------------------
$byApp = @{}
foreach ($g in $grants) {
    $sp = $spById[$g.ClientId]
    if (-not $sp) { continue }

    $key = $sp.AppId
    if (-not $byApp.ContainsKey($key)) {
        $byApp[$key] = [ordered]@{
            app_id     = $sp.AppId
            app_name   = $sp.DisplayName
            publisher  = $sp.PublisherName
            provider   = 'microsoft'
            scopes     = New-Object System.Collections.Generic.HashSet[string]
            _users     = New-Object System.Collections.Generic.HashSet[string]
            user_count = 0
            first_seen = ''
            last_seen  = ''
        }
    }

    # Scope string is space-delimited on the grant.
    foreach ($s in ($g.Scope -split '\s+')) {
        if ($s) { [void]$byApp[$key].scopes.Add($s.Trim()) }
    }

    # ConsentType 'Principal' = one user consented; 'AllPrincipals' = admin consented tenant-wide.
    if ($g.ConsentType -eq 'Principal' -and $g.PrincipalId) {
        [void]$byApp[$key]._users.Add([string]$g.PrincipalId)
    } elseif ($g.ConsentType -eq 'AllPrincipals') {
        $byApp[$key].tenant_wide_admin_consent = $true
    }
}

# --- Shape the output (privacy default: counts, not identities) -------------------
$records = foreach ($k in $byApp.Keys) {
    $a = $byApp[$k]
    $rec = [ordered]@{
        app_id     = $a.app_id
        app_name   = $a.app_name
        publisher  = $a.publisher
        provider   = 'microsoft'
        scopes     = @($a.scopes)
        user_count = $a._users.Count
    }
    if ($a.tenant_wide_admin_consent) { $rec.tenant_wide_admin_consent = $true }
    if ($IncludeUsers) { $rec.users = @($a._users) }   # opt-in ONLY
    [pscustomobject]$rec
}

if (-not $OutFile) {
    $stamp = Get-Date -Format 'yyyyMMdd'
    $OutFile = Join-Path (Get-Location) ("oauth-grants-{0}-{1}.json" -f $ctx.TenantId, $stamp)
}

$payload = [ordered]@{
    generated_utc  = (Get-Date).ToUniversalTime().ToString('o')
    tenant_id      = $ctx.TenantId
    provider       = 'microsoft'
    includes_users = [bool]$IncludeUsers
    grant_count    = ($records | Measure-Object).Count
    grants         = @($records)
}

$payload | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding utf8

Disconnect-MgGraph | Out-Null

Write-Host ''
Write-Host ("Wrote {0} application(s) to:" -f $payload.grant_count) -ForegroundColor Green
Write-Host ("  {0}" -f $OutFile)
Write-Host ''
Write-Host 'OPEN THE FILE AND READ IT before uploading. It contains only what you see there.' -ForegroundColor Yellow
if ($IncludeUsers) {
    Write-Host 'NOTE: -IncludeUsers was set, so this file contains user identifiers.' -ForegroundColor Yellow
}
Write-Host 'Upload it in TRAIGA Auditor: AI Inventory -> Discover OAuth (dry run first).'
Write-Host ''
