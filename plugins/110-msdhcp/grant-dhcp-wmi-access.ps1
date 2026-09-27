<#
.SYNOPSIS
Lets a group read DHCP through WMI over WinRM, for homelab-documenter's
MSDHCP plugin.

.DESCRIPTION
The DHCP PowerShell cmdlets work through the WMI namespace
root/Microsoft/Windows/DHCP. A login over WinRM counts as remote, and WMI
only lets remote logins into a namespace with "Remote Enable", which by
default only administrators have. Without it, Get-DhcpServerv4Scope fails
with "Cannot connect to CIM server. Access denied".

This adds an allow entry for the group on that namespace: Enable Account,
Execute Methods and Remote Enable. It doesn't let the group change DHCP:
what the cmdlets may do is still decided by DHCP Users. Run it on the DHCP
server, in Windows PowerShell as an administrator. Running it again changes
nothing.

.PARAMETER Group
The group to allow (default: DHCP Users; on a domain controller give it
as DOMAIN\DHCP Users).

.EXAMPLE
.\grant-dhcp-wmi-access.ps1
.\grant-dhcp-wmi-access.ps1 -Group 'EXAMPLE\DHCP Users'
#>
param([string]$Group = 'DHCP Users')

$ErrorActionPreference = 'Stop'

$namespace = 'root\Microsoft\Windows\DHCP'
# WBEM_ENABLE (Enable Account) + WBEM_METHOD_EXECUTE (Execute Methods) +
# WBEM_REMOTE_ACCESS (Remote Enable)
$mask = 0x1 + 0x2 + 0x20

$sid = (New-Object System.Security.Principal.NTAccount $Group).Translate(
    [System.Security.Principal.SecurityIdentifier]).Value

$security = Get-WmiObject -Namespace $namespace -Class __SystemSecurity
$descriptor = $security.GetSecurityDescriptor().Descriptor

foreach ($existing in @($descriptor.DACL)) {
    if ($existing.Trustee.SIDString -eq $sid -and $existing.AceType -eq 0 -and
            ($existing.AccessMask -band $mask) -eq $mask) {
        "$Group already has Enable Account, Execute Methods and Remote Enable on $namespace"
        return
    }
}

$trustee = ([wmiclass]'Win32_Trustee').CreateInstance()
$trustee.SIDString = $sid
$ace = ([wmiclass]'Win32_ACE').CreateInstance()
$ace.AccessMask = $mask
$ace.AceFlags = 0      # this namespace only
$ace.AceType = 0       # allow
$ace.Trustee = $trustee

$descriptor.DACL = @($descriptor.DACL) + $ace.PSObject.ImmediateBaseObject
$result = $security.SetSecurityDescriptor($descriptor)
if ($result.ReturnValue -ne 0) {
    throw "SetSecurityDescriptor failed: $($result.ReturnValue)"
}
"Gave $Group Enable Account, Execute Methods and Remote Enable on $namespace"
