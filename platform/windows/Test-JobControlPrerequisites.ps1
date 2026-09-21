[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$requirements = @(
    @{ Name = 'WSL'; Command = 'wsl.exe'; Args = @('--version') },
    @{ Name = 'Docker'; Command = 'docker.exe'; Args = @('--version') },
    @{ Name = 'Docker Compose'; Command = 'docker.exe'; Args = @('compose', 'version') },
    @{ Name = 'Tailscale'; Command = 'tailscale.exe'; Args = @('version') }
)
$failed = $false
foreach ($requirement in $requirements) {
    $command = Get-Command $requirement.Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $executable = if ($command) { $command.Source } else { $null }
    if (-not $executable -and $requirement.Command -eq 'tailscale.exe') {
        $installed = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
        if (Test-Path -LiteralPath $installed -PathType Leaf) { $executable = $installed }
    }
    $status = 'MISSING'
    if ($executable) {
        $arguments = [string[]]$requirement.Args
        & $executable @arguments *> $null
        $status = if ($LASTEXITCODE -eq 0) { 'OK' } else { 'FAILED' }
    }
    if ($status -ne 'OK') { $failed = $true }
    [pscustomobject]@{ Requirement = $requirement.Name; Status = $status }
}
if ($failed) { exit 1 }
