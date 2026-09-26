<#
.SYNOPSIS
Moves the Bitwarden master password from Windows Credential Manager into
the engine's encrypted credentials (#22), without it ever being typed
again, echoed, or put in a file, environment variable or command line.

.DESCRIPTION
Optional: the usual way to store it on any OS is simply
    docker compose run --rm secrets set bw_master_password
which prompts for it. This script is for keeping a copy in Credential
Manager and encrypting from there:

Store it in Credential Manager (prompts; nothing is echoed):
    powershell -File scripts\bw-password.ps1 -Set

Encrypt it as the engine's bw_master_password credential (run from the
engine repo; after this, `docker compose run --rm build` and `preview`
unlock the vault by themselves):
    powershell -File scripts\bw-password.ps1 -Encrypt

Remove the Credential Manager copy:
    powershell -File scripts\bw-password.ps1 -Remove

The Credential Manager copy is a Generic credential named
"homelab-documenter/bitwarden" (Control Panel > Credential Manager >
Windows Credentials), encrypted with your Windows login. Works in Windows
PowerShell 5.1 and PowerShell 7.
#>
[CmdletBinding(DefaultParameterSetName = 'Help')]
param(
    [Parameter(ParameterSetName = 'Set', Mandatory)] [switch] $Set,
    [Parameter(ParameterSetName = 'Remove', Mandatory)] [switch] $Remove,
    [Parameter(ParameterSetName = 'Encrypt', Mandatory)] [switch] $Encrypt
)

$ErrorActionPreference = 'Stop'
$Target = 'homelab-documenter/bitwarden'

# Credential Manager's own API (advapi32), so no module needs installing
Add-Type -Namespace HomelabDocumenter -Name Cred -MemberDefinition @'
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct CREDENTIAL {
    public int Flags; public int Type; public string TargetName;
    public string Comment; public long LastWritten;
    public int CredentialBlobSize; public IntPtr CredentialBlob;
    public int Persist; public int AttributeCount; public IntPtr Attributes;
    public string TargetAlias; public string UserName;
}
[DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool CredWrite(ref CREDENTIAL cred, int flags);
[DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool CredRead(string target, int type, int flags, out IntPtr cred);
[DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool CredDelete(string target, int type, int flags);
[DllImport("advapi32.dll")]
public static extern void CredFree(IntPtr cred);

public static void Write(string target, string user, string secret) {
    byte[] blob = System.Text.Encoding.Unicode.GetBytes(secret);
    CREDENTIAL c = new CREDENTIAL();
    c.Type = 1;                  // CRED_TYPE_GENERIC
    c.Persist = 2;               // CRED_PERSIST_LOCAL_MACHINE
    c.TargetName = target; c.UserName = user;
    c.CredentialBlobSize = blob.Length;
    c.CredentialBlob = Marshal.AllocHGlobal(blob.Length);
    try {
        Marshal.Copy(blob, 0, c.CredentialBlob, blob.Length);
        if (!CredWrite(ref c, 0))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    } finally {
        Marshal.FreeHGlobal(c.CredentialBlob);
        System.Array.Clear(blob, 0, blob.Length);
    }
}
public static string Read(string target) {
    IntPtr p;
    if (!CredRead(target, 1, 0, out p)) return null;
    try {
        CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(p, typeof(CREDENTIAL));
        return Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2);
    } finally { CredFree(p); }
}
public static bool Delete(string target) { return CredDelete(target, 1, 0); }
'@

function Get-StoredPassword {
    $password = [HomelabDocumenter.Cred]::Read($Target)
    if (-not $password) {
        throw "No Bitwarden master password stored. Run: powershell -File scripts\bw-password.ps1 -Set"
    }
    $password
}

# Run docker (compose) from the engine repo with the password on its stdin
# (read by `secrets set`).
# Starting it here, rather than piping, avoids Windows PowerShell 5.1
# re-encoding the pipe (which garbles non-ASCII passwords).
function Invoke-DockerWithPassword([string[]] $DockerArgs) {
    $psi = New-Object Diagnostics.ProcessStartInfo 'docker'
    $psi.Arguments = ($DockerArgs | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join ' '
    $psi.WorkingDirectory = Split-Path -Parent $PSScriptRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $process = [Diagnostics.Process]::Start($psi)
    $stdin = $process.StandardInput.BaseStream
    $bytes = (New-Object Text.UTF8Encoding $false).GetBytes((Get-StoredPassword) + "`n")
    $stdin.Write($bytes, 0, $bytes.Length)
    $stdin.Close()
    $process.WaitForExit()
    $process.ExitCode
}

switch ($PSCmdlet.ParameterSetName) {
    'Set' {
        $secure = Read-Host -AsSecureString 'Bitwarden master password'
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            if (-not $plain) { throw 'Nothing entered; nothing stored.' }
            [HomelabDocumenter.Cred]::Write($Target, 'bitwarden', $plain)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        Write-Host "Stored in Credential Manager as '$Target'."
    }
    'Remove' {
        if ([HomelabDocumenter.Cred]::Delete($Target)) {
            Write-Host "Removed '$Target' from Credential Manager."
        } else {
            Write-Host "Nothing stored under '$Target'."
        }
    }
    'Encrypt' {
        # Stored encrypted to this install's key; the value is never printed
        exit (Invoke-DockerWithPassword @('compose', 'run', '--rm', '-T',
            'secrets', 'set', 'bw_master_password'))
    }
    default {
        Get-Help $PSCommandPath -Detailed
    }
}
