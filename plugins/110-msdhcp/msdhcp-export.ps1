<#
.SYNOPSIS
Exports a Microsoft DHCP server's IPv4 scopes, leases and reservations as
JSON, for homelab-documenter's MSDHCP plugin.

.DESCRIPTION
The MSDHCP plugin runs this same script over WinRM ("mode": "winrm"). For
"mode": "file", run it on the DHCP server (e.g. as a scheduled task) and
put the file where the plugin reads it: input/MSDHCP/msdhcp-export.json in
the content repo. Read-only: it needs membership of DHCP Users, nothing
more.

.PARAMETER OutFile
Write the JSON here (UTF-8) instead of to the output.

.EXAMPLE
.\msdhcp-export.ps1 -OutFile \\fileserver\homelab\input\MSDHCP\msdhcp-export.json
#>
param([string]$OutFile)

$ErrorActionPreference = 'Stop'

$scopes = @(Get-DhcpServerv4Scope)
$leases = @($scopes | ForEach-Object { Get-DhcpServerv4Lease -ScopeId $_.ScopeId })
$reservations = @($scopes | ForEach-Object { Get-DhcpServerv4Reservation -ScopeId $_.ScopeId })

# Addresses and enums as plain strings, so the JSON is the same on every
# Windows version
$export = [ordered]@{
    version      = 1
    server       = [System.Net.Dns]::GetHostEntry('localhost').HostName
    generated    = (Get-Date).ToUniversalTime().ToString('o')
    scopes       = @($scopes | ForEach-Object { [ordered]@{
        ScopeId     = $_.ScopeId.ToString()
        SubnetMask  = $_.SubnetMask.ToString()
        Name        = $_.Name
        Description = $_.Description
        State       = "$($_.State)"
    } })
    leases       = @($leases | ForEach-Object { [ordered]@{
        IPAddress    = $_.IPAddress.ToString()
        ScopeId      = $_.ScopeId.ToString()
        ClientId     = $_.ClientId
        HostName     = $_.HostName
        AddressState = "$($_.AddressState)"
    } })
    reservations = @($reservations | ForEach-Object { [ordered]@{
        IPAddress   = $_.IPAddress.ToString()
        ScopeId     = $_.ScopeId.ToString()
        ClientId    = $_.ClientId
        Name        = $_.Name
        Description = $_.Description
    } })
}

$json = $export | ConvertTo-Json -Depth 4 -Compress
if ($OutFile) {
    [System.IO.File]::WriteAllText($OutFile, $json, (New-Object System.Text.UTF8Encoding $false))
} else {
    $json
}
