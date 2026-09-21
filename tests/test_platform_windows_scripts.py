import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / 'platform' / 'windows'


class WindowsStartupScriptTests(unittest.TestCase):
    def test_start_uses_direct_wsl_arguments_and_private_loopback(self):
        text = (WINDOWS / 'Start-JobControl.ps1').read_text(encoding='utf-8')
        for value in ('startup.json', 'wsl.exe', '--exec', 'start-stack.sh', '127.0.0.1', 'serve', '--json'):
            self.assertIn(value, text)
        self.assertNotIn('bash -lc', text)
        self.assertNotIn('Invoke-Expression', text)
        self.assertNotRegex(text.lower(), r'&[^\n]*\bfunnel\b')
        self.assertIn('AllowFunnel', text)
        self.assertIn('Conflicting', text)
        self.assertIn('WaitForExit(30000)', text)
        self.assertIn('CreateNoWindow = $true', text)

    def test_tailscale_uses_path_lookup_then_installed_fallback(self):
        for name in ('Start-JobControl.ps1', 'Test-JobControlPrerequisites.ps1'):
            text = (WINDOWS / name).read_text(encoding='utf-8')
            self.assertIn('Get-Command', text)
            self.assertIn('Tailscale\\tailscale.exe', text)
            self.assertIn('$LASTEXITCODE', text)

    def test_registration_is_owned_by_current_user(self):
        text = (WINDOWS / 'Install-JobControlStartup.ps1').read_text(encoding='utf-8')
        for value in ('New-ScheduledTaskTrigger -AtLogOn -User $userSid', '-RunLevel Limited',
                      '-LogonType Interactive', 'WindowsIdentity', 'Principal.UserId',
                      '-MultipleInstances IgnoreNew', '-Force', '-StartupConfig'):
            self.assertIn(value, text)
        self.assertNotIn('NT AUTHORITY\\SYSTEM', text)

    def test_serve_configuration_rejects_conflicts_and_requires_exact_private_target(self):
        shell = shutil.which('powershell.exe')
        if not shell:
            self.skipTest('Windows PowerShell unavailable')
        script_path = str(WINDOWS / 'Start-JobControl.ps1').replace("'", "''")
        harness = r'''
$ErrorActionPreference = 'Stop'
$target = 'http://127.0.0.1:3001'
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__SCRIPT__', [ref]$null, [ref]$null)
$function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-PrivateServeConfiguration' }, $true)
. ([scriptblock]::Create($function.Extent.Text))
$valid = '{"TCP":{"443":{"HTTPS":true}},"Web":{"example.test:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:3001"}}}}}' | ConvertFrom-Json
Assert-PrivateServeConfiguration $valid -RequireTarget
Assert-PrivateServeConfiguration ('{}' | ConvertFrom-Json)
$invalid = @(
    '{}',
    '{"TCP":{"443":{"HTTPS":false}}}',
    '{"AllowFunnel":{"example.test:443":true}}',
    '{"TCP":{"443":{"HTTPS":true}},"Web":{"example.test:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:9999"}}}}}'
)
foreach ($json in $invalid) {
    $rejected = $false
    try { Assert-PrivateServeConfiguration ($json | ConvertFrom-Json) -RequireTarget } catch { $rejected = $true }
    if (-not $rejected) { throw 'Unsafe Serve configuration was accepted' }
}
Write-Output 'Serve validation passed'
'''.replace('__SCRIPT__', script_path)
        result = subprocess.run([shell, '-NoProfile', '-Command', harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Serve validation passed', result.stdout)
    def test_bad_startup_values_fail_before_host_commands(self):
        shell = shutil.which('powershell.exe')
        if not shell:
            self.skipTest('Windows PowerShell unavailable')
        good = dict(repo_wsl_path='/mnt/c/repo', private_env_wsl_path='/mnt/c/private/runtime.env',
                    web_port=3001, distro='Ubuntu')
        bad = [('repo_wsl_path', "/mnt/c/repo'; touch /tmp/oops"),
               ('repo_wsl_path', '/mnt/c/repo/../other'),
               ('private_env_wsl_path', '/mnt/c/private\ncommand'),
               ('distro', '--system'), ('distro', 'Ubuntu;whoami'),
               ('web_port', 0), ('web_port', 65536), ('web_port', 3001.5), ('web_port', True)]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'startup.json'
            for key, value in bad:
                with self.subTest(key=key, value=value):
                    config.write_text(json.dumps({**good, key: value}), encoding='utf-8')
                    result = subprocess.run([shell, '-NoProfile', '-File', str(WINDOWS / 'Start-JobControl.ps1'),
                                             '-StartupConfig', str(config)], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Invalid startup configuration', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
