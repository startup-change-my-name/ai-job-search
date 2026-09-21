[CmdletBinding()]
param(
    [string]$ScriptPath,
    [string]$StartupConfig = (Join-Path $env:USERPROFILE 'Documents\ChatGPT\ai-job-search-private\config\job-control\startup.json')
)
$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) { $ScriptPath = Join-Path $PSScriptRoot 'Start-JobControl.ps1' }
foreach ($path in @($ScriptPath, $StartupConfig)) {
    if (-not [System.IO.Path]::IsPathRooted($path) -or $path -match '["\r\n]' -or
        -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'Startup script and configuration must be existing absolute file paths without quotes or newlines.'
    }
}
$ScriptPath = (Resolve-Path -LiteralPath $ScriptPath).ProviderPath
$StartupConfig = (Resolve-Path -LiteralPath $StartupConfig).ProviderPath
$taskName = 'JobControlPlatform'
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$existing = Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object { $_.TaskName -eq $taskName }
if ($existing) {
    $owner = $existing.Principal.UserId
    if ($owner -notmatch '^S-1-') {
        $account = New-Object System.Security.Principal.NTAccount($owner)
        $owner = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
    }
    if ($owner -ne $userSid) { throw 'Existing JobControlPlatform task belongs to a different user; preserved.' }
}
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $powershell `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`" -StartupConfig `"$StartupConfig`"" `
    -WorkingDirectory (Split-Path -Parent $ScriptPath)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userSid
$principal = New-ScheduledTaskPrincipal -UserId $userSid -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
$registered = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
if ($registered.Principal.RunLevel -ne 'Limited' -or $registered.Principal.LogonType -ne 'Interactive' -or
    $registered.Actions.Arguments -ne $action.Arguments) { throw 'Startup task verification failed.' }
Write-Host 'Registered and verified per-user startup task: JobControlPlatform'
