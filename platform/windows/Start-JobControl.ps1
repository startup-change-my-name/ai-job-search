[CmdletBinding()]
param(
    [string]$StartupConfig = (Join-Path $env:USERPROFILE 'Documents\ChatGPT\ai-job-search-private\config\job-control\startup.json')
)
$ErrorActionPreference = 'Stop'

# Validate before any native command. Paths are data passed directly to bash, never shell code.
$config = Get-Content -LiteralPath $StartupConfig -Raw | ConvertFrom-Json
foreach ($field in @('repo_wsl_path', 'private_env_wsl_path')) {
    $value = $config.$field
    if ($value -isnot [string] -or $value -cnotmatch '^/mnt/[a-z]/[A-Za-z0-9_./ -]+$' -or
        $value -match '(^|/)\.{1,2}(/|$)|//|/$' -or $value -match '[\r\n]') {
        throw "Invalid startup configuration: $field must be a canonical mounted-drive path."
    }
}
if ($config.distro -isnot [string] -or $config.distro -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' -or $config.distro -match '[\r\n]') {
    throw 'Invalid startup configuration: invalid WSL distribution name.'
}
if (($config.web_port -isnot [int] -and $config.web_port -isnot [long]) -or
    $config.web_port -lt 1 -or $config.web_port -gt 65535) {
    throw 'Invalid startup configuration: web_port must be an integer from 1 through 65535.'
}
$port = [int]$config.web_port
$target = "http://127.0.0.1:$port"
$command = Get-Command tailscale.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$tailscale = if ($command) { $command.Source } else { Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
if (-not (Test-Path -LiteralPath $tailscale -PathType Leaf)) { throw 'Tailscale is not installed.' }

function Get-ServeConfiguration {
    $raw = & $tailscale serve status --json 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Tailscale Serve configuration.' }
    try { $result = ($raw -join "`n") | ConvertFrom-Json } catch { throw 'Invalid Tailscale Serve status response.' }
    if ($null -eq $result) { throw 'Tailscale Serve status was empty.' }
    return $result
}
function Assert-PrivateServeConfiguration($Status, [switch]$RequireTarget) {
    # Refuse pre-existing public exposure rather than changing unrelated host state.
    foreach ($property in $Status.AllowFunnel.PSObject.Properties) {
        if ($property.Value -eq $true) { throw 'Conflicting public exposure exists in the Tailscale configuration.' }
    }
    $listener = $Status.TCP.'443'
    if ($null -ne $listener -and $listener.HTTPS -ne $true) {
        throw 'Conflicting Tailscale listener already uses port 443.'
    }
    $rootHandlerCount = 0
    foreach ($endpoint in $Status.Web.PSObject.Properties) {
        if ($endpoint.Name -notmatch ':443$') { continue }
        $rootHandler = $endpoint.Value.Handlers.'/'
        if ($null -eq $rootHandler) { continue }
        if ($rootHandler.Proxy -ne $target -or $rootHandler.Path -or $rootHandler.Text) {
            throw 'Conflicting Tailscale Serve root handler; existing service was preserved.'
        }
        $rootHandlerCount++
    }
    if ($RequireTarget -and ($rootHandlerCount -ne 1 -or $listener.HTTPS -ne $true)) {
        throw 'Tailscale Serve did not confirm the private loopback dashboard target.'
    }
}
Assert-PrivateServeConfiguration (Get-ServeConfiguration)

$startScript = $config.repo_wsl_path + '/platform/scripts/start-stack.sh'
& wsl.exe --distribution $config.distro --exec bash $startScript $config.private_env_wsl_path
if ($LASTEXITCODE -ne 0) { throw "WSL stack start failed with exit code $LASTEXITCODE" }
$client = New-Object System.Net.Sockets.TcpClient
try {
    $connection = $client.ConnectAsync('127.0.0.1', $port)
    if (-not $connection.Wait(5000) -or -not $client.Connected) { throw 'Dashboard loopback listener is unavailable.' }
} finally { $client.Dispose() }
# Recheck immediately before mutation and preserve all other Serve handlers.
Assert-PrivateServeConfiguration (Get-ServeConfiguration)
$serveProcess = New-Object System.Diagnostics.Process
$serveProcess.StartInfo.FileName = $tailscale
$serveProcess.StartInfo.Arguments = "serve --bg --https=443 --set-path=/ --yes $target"
$serveProcess.StartInfo.UseShellExecute = $false
$serveProcess.StartInfo.CreateNoWindow = $true
$serveProcess.StartInfo.RedirectStandardOutput = $true
$serveProcess.StartInfo.RedirectStandardError = $true
try {
    if (-not $serveProcess.Start()) { throw 'Could not start the Tailscale Serve command.' }
    $standardOutput = $serveProcess.StandardOutput.ReadToEndAsync()
    $standardError = $serveProcess.StandardError.ReadToEndAsync()
    if (-not $serveProcess.WaitForExit(30000)) {
        $serveProcess.Kill()
        $serveProcess.WaitForExit()
        throw 'Tailscale Serve setup timed out; check that Serve and HTTPS are enabled in the Tailscale admin console, then retry.'
    }
    if ($serveProcess.ExitCode -ne 0) { throw 'Tailscale Serve failed; check Tailscale connection and HTTPS permissions.' }
} finally { $serveProcess.Dispose() }
Assert-PrivateServeConfiguration (Get-ServeConfiguration) -RequireTarget
Write-Host 'Job Control stack is healthy and its private Tailscale Serve route is verified.'
