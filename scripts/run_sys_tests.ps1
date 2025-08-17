# Run only system tests (marked @pytest.mark.system) with the required env var.
# Keeps output concise (no XML, no slowest list), shows the usual pytest summary.
#
# Usage:
# .\scripts\run_system_tests.ps1 
#
# Notes:
# - Uses `poetry run` when Poetry + pyproject.toml are present; otherwise falls back to `pytest`.
# - Forces a headless backend for any plots generated during tests.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir '..')

# Collect test paths (default: tests/system)
if ($args.Count -ge 1) {
  $TestPaths = $args
} else {
  $TestPaths = @('tests/system')
}

# Decide runner prefix
$UsePoetry = (Get-Command poetry -ErrorAction SilentlyContinue) -ne $null -and
             (Test-Path (Join-Path $RepoRoot 'pyproject.toml'))
$Runner = if ($UsePoetry) { 'poetry run pytest' } else { 'pytest' }

# Set env vars for this process
$env:MPLBACKEND = if ($env:MPLBACKEND) { $env:MPLBACKEND } else { 'Agg' }
$env:ASYNCFLOW_RUN_SYSTEM_TESTS = '1'

Push-Location $RepoRoot
try {
  Write-Host "==> Running system tests…"
  # Clear any configured addopts and run only system-marked tests
  $pytestArgs = @(
    '-o', 'addopts=',
    '-m', 'system',
    '--disable-warnings',
    '-q'
  ) + $TestPaths

  if ($UsePoetry) {
    poetry run pytest @pytestArgs
  } else {
    pytest @pytestArgs
  }

  Write-Host "✅ System tests PASSED"
}
finally {
  Pop-Location
}
