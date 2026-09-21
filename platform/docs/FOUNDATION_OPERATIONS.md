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

For an explicitly approved clean credential rotation: stop Serve, run `compose down` without volume removal, and back up the private environment and databases to private storage. Recreate the private environment from `platform/runtime.env.template` using fresh, independent cryptographically random values for `POSTGRES_PASSWORD`, `INTERNAL_PROXY_TOKEN`, and `AIRFLOW_JWT_SECRET`; preserve the private identity, paths, image versions, port, and database names. The internal token must match in web/API; merely changing a password environment variable does not change an existing PostgreSQL user's password.

Only after accepting the data loss, identify and remove the stopped project's PostgreSQL volume (leave Airflow log volume intact):

```bash
# Deliberately separate this from everyday recovery commands. Confirm the exact name first.
"${compose[@]}" config --volumes
# Destructive; run only for the intentional clean rebuild described above:
docker volume rm job-control_postgres-data
# If using the Windows fallback, use docker.exe for that single command instead.
chmod 600 "$env_file"
./platform/scripts/start-stack.sh "$env_file"
```

The Compose project name is `job-control`; verify the actual volume name before deletion. Re-run the Windows launcher to restore Serve, then all isolation/authentication checks. Never print the new values, commit the private environment, or capture rendered `docker compose config` output.

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
