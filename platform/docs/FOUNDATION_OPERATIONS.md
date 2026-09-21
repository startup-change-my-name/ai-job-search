# Job Control foundation operations

This is the service foundation: the cockpit shows real PostgreSQL/Airflow health, while job queues are placeholders. Discovery, applications, and email reminders are subsequent work. Access is private through Tailscale Serve; Funnel must stay disabled. The current deployment uses **3001**; the reusable template defaults to 3000. Always read the configured port rather than assuming either value.

## Windows setup and start

Run in PowerShell as the same interactive Windows user who owns the registered task:

```powershell
$repo = Join-Path $env:USERPROFILE 'Documents\ChatGPT\ai-job-search\.worktrees\job-control-foundation'
$startup = Join-Path $env:USERPROFILE 'Documents\ChatGPT\ai-job-search-private\config\job-control\startup.json'
$config = Get-Content -LiteralPath $startup -Raw | ConvertFrom-Json
$port = [int]$config.web_port
$tsCommand = Get-Command tailscale.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$tailscale = if ($tsCommand) { $tsCommand.Source } else { Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
& "$repo\platform\windows\Test-JobControlPrerequisites.ps1"
wsl.exe --list --verbose
docker.exe version
& $tailscale version
& "$repo\platform\windows\Start-JobControl.ps1" -StartupConfig $startup
```

Docker Desktop must have its Linux engine running, the configured WSL distribution must exist, and Tailscale must be signed in. The prerequisite script checks executable versions; `docker.exe version` checks engine availability. The launcher validates the private configuration, starts the stack, waits for all nine services and dependencies, then verifies the private HTTPS proxy. A conflicting existing Serve root or any Funnel exposure stops startup for inspection.

Register or refresh the per-user, limited-privilege logon task after moving the worktree or configuration:

```powershell
& "$repo\platform\windows\Install-JobControlStartup.ps1" -ScriptPath "$repo\platform\windows\Start-JobControl.ps1" -StartupConfig $startup
Get-ScheduledTask -TaskName JobControlPlatform | Select-Object State,@{n='RunLevel';e={$_.Principal.RunLevel}},@{n='LogonType';e={$_.Principal.LogonType}}
```

Expected principal: `Limited`, `Interactive`. Keep the worktree at its registered path until you re-register it. The task runs at user logon, including on battery, and retries failures three times at one-minute intervals; it does not run before login.

## WSL service inspection

From PowerShell, open the configured distribution, then run the Bash block using the two paths from the private `startup.json` (do not display `runtime.env`):

```powershell
wsl.exe --distribution $config.distro
```

```bash
# Adapt these two paths if the private startup configuration was moved.
repo="/mnt/c/Users/$(cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/Documents/ChatGPT/ai-job-search/.worktrees/job-control-foundation"
env_file="/mnt/c/Users/$(cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/Documents/ChatGPT/ai-job-search-private/config/job-control/runtime.env"
cd "$repo"
# Match the lifecycle scripts' native-Docker / Windows-Docker fallback.
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$repo/platform/compose.yaml")
else
  private_path=$(sed -n 's/^PRIVATE_WORKSPACE_PATH=//p' "$env_file" | tr -d '\r')
  export PRIVATE_WORKSPACE_PATH="$(wslpath -w "$private_path")"
  export WSLENV="${WSLENV:+$WSLENV:}PRIVATE_WORKSPACE_PATH"
  compose=(docker.exe compose --env-file "$(wslpath -w "$env_file")" -f "$(wslpath -w "$repo/platform/compose.yaml")")
fi
./platform/scripts/verify-stack.sh "$env_file"
"${compose[@]}" ps
"${compose[@]}" exec -T airflow-api-server airflow dags list
"${compose[@]}" exec -T airflow-api-server airflow dags list-import-errors
# Inspect locally: logs can contain private operational information.
"${compose[@]}" logs --tail 100 api web airflow-scheduler
stat -c '%a' "$env_file"
```

Expect nine long-running services healthy; `airflow-init` completes with exit 0. `platform_health` must be listed and import errors empty. The runtime file should be mode 600 with WSL metadata enabled. Windows ACLs must also restrict the private directory to the intended user and necessary system/administrator principals.

This host has `[automount] options = "metadata,umask=077,fmask=077"` in `/etc/wsl.conf`. Preserve other mount settings when configuring another host. Without metadata, Windows-mounted files can appear as mode 777 even when Windows ACLs are restrictive. After changing this setting, terminate only the configured Ubuntu distribution, restart it, and run `chmod 600` on the private environment; do not globally shut down WSL to apply it. Verify both WSL mode and Windows ACLs.

## Isolation and browser verification

PowerShell, continuing with the variables from setup:

```powershell
Get-NetTCPConnection -State Listen -LocalPort $port | Select-Object LocalAddress,LocalPort
curl.exe --silent --output NUL --write-out '%{http_code}' "http://127.0.0.1:$port/"
# Choose the active Wi-Fi/Ethernet address, not loopback, WSL, VPN, or Tailscale.
$lanIp = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1 -ExpandProperty IPv4Address | Select-Object -ExpandProperty IPAddress
Test-NetConnection -ComputerName $lanIp -Port $port -InformationLevel Quiet
```

Expected: HTTP 403 without identity and LAN TCP result `False`. Docker should publish only `127.0.0.1:<configured port> -> 3000` for web; database, Redis, Airflow, and API ports stay unpublished. Docker Desktop forwarding may not appear as a normal loopback listener in `Get-NetTCPConnection`, so confirm its binding with `compose ps`; inspect any unexpected Windows listener separately. For stronger LAN isolation evidence, repeat the LAN test from another LAN device.

Install the locked browser tools once and run desktop/Pixel 7 checks with the actual Tailscale login held only in process memory:

```powershell
Push-Location "$repo\platform\frontend"
npm ci
npx playwright install chromium
$env:JOB_CONTROL_TEST_URL = "http://127.0.0.1:$port"
$tsStatus = (& $tailscale status --json | Out-String) | ConvertFrom-Json
$env:JOB_CONTROL_TEST_IDENTITY = $tsStatus.User.PSObject.Properties[[string]$tsStatus.Self.UserID].Value.LoginName
if (-not $env:JOB_CONTROL_TEST_IDENTITY) { throw 'Tailscale user login unavailable' }
try { npm run test:e2e } finally {
  Remove-Item Env:JOB_CONTROL_TEST_IDENTITY -ErrorAction SilentlyContinue
  Remove-Item Env:JOB_CONTROL_TEST_URL -ErrorAction SilentlyContinue
  Pop-Location
}
```

The tests cover healthy dependency cards, no horizontal page overflow, reachable 44px touch targets, the authorized API, and HTTP 403 on both page and API for missing/unapproved identities. Local synthetic headers test the app allowlist under the trusted-single-user-PC model. They do not prove real Tailscale identity injection.

For genuine Serve verification, derive the private URL without sending a synthetic header:

```powershell
$serve = (& $tailscale serve status --json | Out-String) | ConvertFrom-Json
if (@($serve.AllowFunnel.PSObject.Properties | Where-Object Value -eq $true).Count) { throw 'Public Funnel exposure detected' }
$endpoint = $serve.Web.PSObject.Properties | Where-Object { $_.Name -match ':443$' -and $_.Value.Handlers.'/'.Proxy -eq "http://127.0.0.1:$port" } | Select-Object -First 1
if (-not $endpoint) { throw 'Expected private Serve route missing' }
$serveUrl = 'https://' + ($endpoint.Name -replace ':443$','')
# Use privately; do not paste status JSON or the hostname into public reports.
Start-Process $serveUrl
```

On the physical phone, connect Tailscale to the same tailnet using the allowlisted identity and open this HTTPS URL in the phone browser. Confirm both cards are healthy/readable with no horizontal scrolling and the bottom navigation is touchable. Record the result privately. If a second non-allowlisted tailnet identity is available, confirm 403 with that identity; do not disrupt the working allowlist solely to simulate a second user. The automated negative tests already cover exact app authorization. A host request to its own Serve URL may not traverse Tailscale peer authentication on every platform; it never substitutes for the physical-phone check.

## Stop and recover without data loss

To stop this application's Serve root while preserving unrelated handlers:

```powershell
& $tailscale serve --https=443 --set-path=/ off
```

If the machine's entire Serve configuration belongs only to Job Control, `& $tailscale serve reset` is an alternative; it removes all Serve handlers on this machine. From the WSL session with the `compose` array above:

```bash
"${compose[@]}" down
```

Do not add `--volumes` or `-v`. The named PostgreSQL and Airflow log volumes persist. Restart with `Start-JobControl.ps1`. If Docker reports stale socket errors, collect local diagnostics and repair Docker Desktop first; do not delete database volumes or reset Docker data to repair a socket.

**Known host limitation, observed during verification:** forced global `wsl --shutdown` reproducibly left Docker Desktop unable to start its Ingest/Secrets Engine AF_UNIX sockets. The registered startup task succeeded after Docker Desktop was repaired, but unattended recovery from this failure is not verified. Runtime socket repair belongs to Docker Desktop troubleshooting; no startup script deletes or renames AppData sockets. Do not reset Docker data or delete volumes for this failure.

For routine Ubuntu recovery on this host, save work and terminate only the configured distribution:

```powershell
wsl.exe --terminate $config.distro
Start-ScheduledTask -TaskName JobControlPlatform
# Poll until the task is Ready, allowing startup/build and health checks to finish.
Get-ScheduledTask -TaskName JobControlPlatform | Select-Object State
Get-ScheduledTaskInfo -TaskName JobControlPlatform | Select-Object LastRunTime,LastTaskResult
```

Expected after completion: `LastTaskResult = 0`, all nine services healthy through `verify-stack.sh`, the Serve route restored, no `AllowFunnel=true`, loopback 403 without identity, and phone HTTPS access restored. A running task may temporarily show result 267009. After Windows reboot, sign into the same user; Docker Desktop must start and become ready for the task. A full `wsl --shutdown` rehearsal affects every WSL workload and Docker Desktop; defer repeating it until the known socket failure is resolved. Normal Windows reboot and physical-phone recovery remain distinct checks; do not infer them from the successful task run.

## Credential rotation: intentional destructive rebuild only

**Deleting the PostgreSQL volume destroys both application and Airflow metadata. Never use volume deletion for ordinary stop, restart, socket repair, or routine recovery.** This foundation has no production job history yet; once it does, back up and test restoring both databases first or rotate database credentials in place.

For an explicitly approved clean rebuild, run the following PowerShell blocks in order in the same session, continuing with `$repo`, `$startup`, `$config`, and `$tailscale` from setup. These commands retain the configured port (currently 3001), identities, paths, image versions, and every unrelated environment value. They do not shell-source the environment or display its contents. If either database has valuable state, take and test a private database backup first; the environment backup below contains credentials, not database data.

First stop the task's automatic trigger and the services without deleting data. Do not proceed if the task is currently running. Native command failures stop the procedure explicitly:

```powershell
$ErrorActionPreference = 'Stop'
$rotationTask = Get-ScheduledTask -TaskName JobControlPlatform
if ($rotationTask.State -eq 'Running') { throw 'Wait for the current startup task to finish before rotation.' }
$reenableTask = $rotationTask.State -ne 'Disabled'
Disable-ScheduledTask -TaskName JobControlPlatform | Out-Null
& $tailscale serve --https=443 --set-path=/ off
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the private Serve root.' }
$runtime = (& wsl.exe --distribution $config.distro --exec wslpath -w $config.private_env_wsl_path | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw 'Runtime path unavailable.' }
$composeArgs = @('compose', '--env-file', $runtime, '-f', (Join-Path $repo 'platform\compose.yaml'))
# Windows Compose needs the Windows form of the private bind-mount path.
$privateLine = @(Get-Content -LiteralPath $runtime | Where-Object { $_ -match '^PRIVATE_WORKSPACE_PATH=' })
if ($privateLine.Count -ne 1) { throw 'Expected exactly one private workspace path.' }
$privateWsl = $privateLine[0].Substring('PRIVATE_WORKSPACE_PATH='.Length).TrimEnd("`r")
$oldPrivateOverride = [Environment]::GetEnvironmentVariable('PRIVATE_WORKSPACE_PATH', 'Process')
$env:PRIVATE_WORKSPACE_PATH = (& wsl.exe --distribution $config.distro --exec wslpath -w $privateWsl | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Private workspace conversion failed.' }
& docker.exe @composeArgs down
if ($LASTEXITCODE -ne 0) { throw 'Stack stop failed; do not rotate.' }
```

Prepare a timestamped private backup and validate all new values before replacing the environment. The parser preserves literal dotenv values, comments, ordering, and unrelated keys; it rejects duplicates and malformed entries. The three replacement secrets are independent 32-byte random hex strings, safe for the existing database URL and Compose interpolation. Empty files are secured before any secret bytes are written:

```powershell
function Read-RotationEnv([string]$text) {
    $values = [ordered]@{}
    foreach ($line in ($text -split '\r?\n')) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line -match '^\s*#') { continue }
        if ($line -cnotmatch '^([A-Z][A-Z0-9_]*)=(.*)$') { throw 'Malformed environment entry.' }
        $key, $value = $Matches[1], $Matches[2]
        if ($values.Contains($key)) { throw 'Duplicate environment key.' }
        if ([string]::IsNullOrWhiteSpace($value) -or $value -in @('""', "''")) { throw 'Empty environment value.' }
        $values[$key] = $value
    }
    return ,$values
}
$ownerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
function Protect-RotationFile([string]$path) {
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($ownerSid)
    foreach ($sid in @($ownerSid, $systemSid)) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $path -AclObject $acl
    $wslPath = (& wsl.exe --distribution $config.distro --exec wslpath -u $path | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Permission path conversion failed.' }
    & wsl.exe --distribution $config.distro --exec chmod 600 $wslPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not set private mode.' }
    $mode = (& wsl.exe --distribution $config.distro --exec stat -c '%a' $wslPath | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $mode -ne '600') { throw 'WSL metadata/mode 600 required.' }
    $actual = Get-Acl -LiteralPath $path
    $sids = @($actual.Access | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value })
    if (-not $actual.AreAccessRulesProtected -or $actual.Access.Count -ne 2 -or
        $ownerSid.Value -notin $sids -or 'S-1-5-18' -notin $sids -or
        $actual.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $ownerSid.Value) {
        throw 'Private owner/SYSTEM ACL validation failed.'
    }
}
Protect-RotationFile $runtime
$oldBytes = [System.IO.File]::ReadAllBytes($runtime)
$original = [System.IO.File]::ReadAllText($runtime)
$oldValues = Read-RotationEnv $original
$required = Read-RotationEnv ([System.IO.File]::ReadAllText((Join-Path $repo 'platform\runtime.env.template')))
foreach ($key in $required.Keys) {
    if (-not $oldValues.Contains($key)) { throw 'Required runtime key missing.' }
}
$rotatedKeys = @('POSTGRES_PASSWORD', 'INTERNAL_PROXY_TOKEN', 'AIRFLOW_JWT_SECRET')
$newSecrets = @{}
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($key in $rotatedKeys) {
        do {
            $bytes = New-Object byte[] 32
            $rng.GetBytes($bytes)
            $value = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        } while ($value -in @($oldValues.Values) -or $value -in @($newSecrets.Values))
        $newSecrets[$key] = $value
    }
} finally { $rng.Dispose() }
$replacement = [regex]::Replace($original,
    '(?m)^(POSTGRES_PASSWORD|INTERNAL_PROXY_TOKEN|AIRFLOW_JWT_SECRET)=[^\r\n]*',
    [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $match.Groups[1].Value + '=' + $newSecrets[$match.Groups[1].Value] })
$newValues = Read-RotationEnv $replacement
if ($newValues.Count -ne $oldValues.Count) { throw 'Environment key count changed.' }
foreach ($key in $oldValues.Keys) {
    if (-not $newValues.Contains($key)) { throw 'Environment key lost.' }
    if ($key -in $rotatedKeys) {
        if ($newValues[$key] -cnotmatch '^[a-f0-9]{64}$' -or $newValues[$key] -eq $oldValues[$key]) { throw 'New secret validation failed.' }
    } elseif ($newValues[$key] -cne $oldValues[$key]) { throw 'Unrelated value changed.' }
}
if (@($rotatedKeys | ForEach-Object { $newValues[$_] } | Select-Object -Unique).Count -ne 3) { throw 'Secrets must be independent.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$backup = $runtime + '.backup-' + $stamp
$temp = $runtime + '.rotate-' + [Guid]::NewGuid().ToString('N') + '.tmp'
# CreateNew prevents accidental overwrite; files are empty until ACL/mode checks pass.
foreach ($path in @($backup, $temp)) {
    $handle = [System.IO.File]::Open($path, [System.IO.FileMode]::CreateNew)
    $handle.Dispose()
    Protect-RotationFile $path
}
[System.IO.File]::WriteAllBytes($backup, $oldBytes)
[System.IO.File]::WriteAllText($temp, $replacement, (New-Object System.Text.UTF8Encoding($false)))
if ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($backup)) -cne [Convert]::ToBase64String($oldBytes)) { throw 'Backup verification failed.' }
if ([System.IO.File]::ReadAllText($temp) -cne $replacement) { throw 'Temporary file verification failed.' }
# Quiet validation only: never render the substituted Compose configuration.
& docker.exe compose --env-file $temp -f (Join-Path $repo 'platform\compose.yaml') config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose rejected the new environment; original remains intact.' }
Protect-RotationFile $backup
Protect-RotationFile $temp
# Atomic replacement on the same NTFS directory; the separate backup is retained privately.
[System.IO.File]::Replace($temp, $runtime, $null)
Protect-RotationFile $runtime
if ([System.IO.File]::ReadAllText($runtime) -cne $replacement) { throw 'Final environment verification failed.' }
Write-Host 'Private backup and validated credential replacement complete; database volume is still intact.'
```

If preparation fails, leave the task disabled and services stopped, inspect the failure without printing environment contents, and restore the secured backup before starting with the old database. Changing `POSTGRES_PASSWORD` in the environment does not change an existing database user's password. The three rotated keys now coexist only in the private file and local process memory.

**Destructive boundary:** the following block destroys both databases. Run it only after explicitly choosing the clean rebuild and accepting that loss. It verifies the exact stopped project's volume labels before removing **only** `job-control_postgres-data`; the Airflow log volume stays intact. The typed confirmation prevents accidental execution when copying the whole runbook:

```powershell
$volume = 'job-control_postgres-data'
$volumeInfo = (& docker.exe volume inspect $volume | Out-String) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or @($volumeInfo).Count -ne 1 -or
    $volumeInfo[0].Name -ne $volume -or
    $volumeInfo[0].Labels.'com.docker.compose.project' -ne 'job-control' -or
    $volumeInfo[0].Labels.'com.docker.compose.volume' -ne 'postgres-data') { throw 'Unexpected PostgreSQL volume; preserved.' }
$users = @(& docker.exe ps -aq --filter "volume=$volume")
if ($LASTEXITCODE -ne 0 -or $users.Count -ne 0) { throw 'Volume still has a container; preserved.' }
if ((Read-Host 'Type DELETE job-control_postgres-data to destroy both databases') -cne 'DELETE job-control_postgres-data') { throw 'Deletion cancelled; restore old environment before restarting the old database.' }
& docker.exe volume rm $volume
if ($LASTEXITCODE -ne 0) { throw 'Volume removal failed; do not continue.' }
# Restore the caller's process environment before the WSL launcher handles its own paths.
[Environment]::SetEnvironmentVariable('PRIVATE_WORKSPACE_PATH', $oldPrivateOverride, 'Process')
& "$repo\platform\windows\Start-JobControl.ps1" -StartupConfig $startup
& wsl.exe --distribution $config.distro --exec bash ($config.repo_wsl_path + '/platform/scripts/verify-stack.sh') $config.private_env_wsl_path
if ($LASTEXITCODE -ne 0) { throw 'Restart verification failed; leave the scheduled task disabled.' }
if ($reenableTask) { Enable-ScheduledTask -TaskName JobControlPlatform | Out-Null }
Remove-Variable original,replacement,oldBytes,oldValues,newValues,newSecrets,value,bytes -ErrorAction SilentlyContinue
Write-Host 'Clean credential rebuild verified. Repeat browser, isolation, and private Serve checks.'
```

Keep the timestamped backup private; it contains the previous secrets. Repeat all browser/isolation checks above, including the real phone check. Never commit either environment file or share raw Compose configuration. If stopping partway through, restore the process `PRIVATE_WORKSPACE_PATH` override and keep the automatic task disabled until the environment and database credentials agree.

## Diagnostics and regression checks

### Docker MCP browser tooling

The local Docker MCP profile ID `job_control` (display name `job-control`) provides an isolated, catalog-pinned Playwright server to Codex. Compose remains responsible for starting and stopping this platform's containers. Verify the MCP profile and exposed tools separately:

```powershell
docker.exe mcp profile show job_control
docker.exe mcp tools --gateway-arg=--profile --gateway-arg=job_control ls --format list
```

The profile was verified with 31 tools. The local Codex connection launches `docker.exe mcp gateway run --profile job_control`; keep its global client configuration private. An existing Codex session may require restarting to discover the newly connected tools. The committed npm Playwright suite remains a repeatable regression check independent of the interactive MCP browser tools.

Safe starting points are prerequisite results, redacted `compose ps`, health summaries, scheduled-task result, Docker/WSL versions, and import-error counts. Avoid `Get-Content runtime.env`, full `docker inspect`, rendered Compose configuration, environment dumps, Tailscale status JSON in reports, and raw logs in public artifacts. Review any local logs before sharing them. Browser traces/screenshots/videos are disabled by default, and Playwright output folders are Git-ignored.

```powershell
Set-Location $repo
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\platform\backend\.venv\Scripts\python.exe -m pytest platform/backend/tests -v -W error
Push-Location platform/frontend
npm test
npm run lint
npm run build
Pop-Location
```

Then repeat the browser checks and WSL verifier above. The automated suite cannot establish physical-phone access; retain that as a separate human verification item until observed.
