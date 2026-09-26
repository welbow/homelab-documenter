<#
.SYNOPSIS
Keeps the Bitwarden master password in Windows Credential Manager and hands
it to the engine through a pipe (--password-stdin), so it is never in a
file, an environment variable or on a command line.

.DESCRIPTION
Store it once (prompts; nothing is echoed):
    powershell -File scripts\bw-password.ps1 -Set

Then run unattended, from the engine repo:
    powershell -File scripts\bw-password.ps1 -Run build      # export
    powershell -File scripts\bw-password.ps1 -Run preview    # preview

Or pipe it yourself (from cmd, Git Bash or PowerShell 7.4+; Windows
PowerShell 5.1 re-encodes pipes between programs, so use -Run there):
    powershell -File scripts\bw-password.ps1 | docker compose run --rm -T build --password-stdin

Remove it again:
    powershell -File scripts\bw-password.ps1 -Remove

The password is stored as a Generic credential named
"homelab-documenter/bitwarden" (visible in Control Panel > Credential
Manager > Windows Credentials), encrypted with your Windows login. Anyone
who can run programs as you can read it, like any saved credential.
Works in Windows PowerShell 5.1 and PowerShell 7.
#>
[CmdletBinding(DefaultParameterSetName = 'Print')]
param(
    [Parameter(ParameterSetName = 'Set', Mandatory)] [switch] $Set,
    [Parameter(ParameterSetName = 'Remove', Mandatory)] [switch] $Remove,
    [Parameter(ParameterSetName = 'Run', Mandatory)]
    [ValidateSet('build', 'preview')] [string] $Run,
    [Parameter(ParameterSetName = 'Run', ValueFromRemainingArguments)]
    [string[]] $ExtraArgs
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
    'Print' {
        # UTF-8 without a byte-order mark, one line, for --password-stdin
        $stdout = [Console]::OpenStandardOutput()
        $bytes = (New-Object Text.UTF8Encoding $false).GetBytes((Get-StoredPassword) + "`n")
        $stdout.Write($bytes, 0, $bytes.Length)
        $stdout.Flush()
    }
    'Run' {
        # Run docker compose here, from the engine repo, with the password on
        # its stdin; this avoids the shell re-encoding a pipe
        $repo = Split-Path -Parent $PSScriptRoot
        $dockerArgs = @('compose', 'run', '--rm', '-T')
        if ($Run -eq 'preview') { $dockerArgs += '--service-ports' }
        $dockerArgs += @($Run, '--password-stdin') + @($ExtraArgs | Where-Object { $_ })

        $psi = New-Object Diagnostics.ProcessStartInfo 'docker'
        $psi.Arguments = ($dockerArgs | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }) -join ' '
        $psi.WorkingDirectory = $repo
        $psi.UseShellExecute = $false
        $psi.RedirectStandardInput = $true
        $process = [Diagnostics.Process]::Start($psi)
        $stdin = $process.StandardInput.BaseStream
        $bytes = (New-Object Text.UTF8Encoding $false).GetBytes((Get-StoredPassword) + "`n")
        $stdin.Write($bytes, 0, $bytes.Length)
        $stdin.Close()
        $process.WaitForExit()
        exit $process.ExitCode
    }
}
