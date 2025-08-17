# Run tests with coverage ONLY (no XML, no durations), showing pytest’s usual summary.
# It also overrides any configured addopts (e.g. durations/xml) via `-o addopts=`.
#
# Usage:
#   .\scripts\run_tests.ps1 

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Pick test paths
[string[]]$TestPaths = if ($args.Count -ge 1) { $args } else { @('tests') }

# Resolve repo root (this script lives in scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir '..')

# Use Poetry if available and pyproject exists
$RunWithPoetry = (Get-Command poetry -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $RepoRoot 'pyproject.toml'))

# Headless backend if plots are generated during tests
if (-not $env:MPLBACKEND) { $env:MPLBACKEND = 'Agg' }

Set-Location $RepoRoot

# Build command
$cmd = @()
if ($RunWithPoetry) { $cmd += @('poetry', 'run') }
$cmd += 'pytest'
$cmd += @(
  '-o', 'addopts=',
  '--cov=src',
  '--cov-report=term',
  '--disable-warnings',
  '-q'
)
$cmd += $TestPaths

# Execute
& $cmd
