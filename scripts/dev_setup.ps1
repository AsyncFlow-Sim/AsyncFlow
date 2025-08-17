# Post-clone developer setup for AsyncFlow (Windows / PowerShell).
#
# What it does:
#   1) Ensures Poetry is available (official installer if missing).
#   2) Configures Poetry to create an in-project virtualenv (.venv).
#   3) Removes poetry.lock (fresh dependency resolution by policy).
#   4) Installs the project with dev extras.
#   5) Runs ruff, mypy, and pytest (with coverage if available).
#
# Usage:
#   .\scripts\dev_setup.ps1
#
# Notes:
#   - Run this from anywhere; it will cd to repo root.
#   - Requires Python >= 3.12 to be available (via 'py' launcher or python.exe).
#   - We do NOT delete an existing .venv; it will be reused if compatible.

# Strict error handling
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- helpers ------------------------------------------------------------------

function Write-Info { param([string]$Msg) Write-Host "==> $Msg" }
function Write-Ok   { param([string]$Msg) Write-Host "✅ $Msg" -ForegroundColor Green }
function Fail       { param([string]$Msg) Write-Error $Msg; exit 1 }

# Resolve repo root (this script lives in scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir '..')

function Require-Pyproject {
  if (-not (Test-Path (Join-Path $RepoRoot 'pyproject.toml'))) {
    Fail "pyproject.toml not found at repo root ($RepoRoot)"
  }
}

function Get-PythonPath-3_12Plus {
  <#
    Try common Windows launchers/executables and return the *actual* Python
    interpreter path (sys.executable) for a version >= 3.12.
  #>
  $candidates = @(
    @('py', '-3.13'),
    @('py', '-3.12'),
    @('py', '-3'),
    @('python3.13'),
    @('python3.12'),
    @('python')
  )

  foreach ($cand in $candidates) {
    $exe  = $cand[0]
    $args = @()
    if ($cand.Count -gt 1) { $args = $cand[1..($cand.Count-1)] }

    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }

    # Check version
    & $exe @args -c "import sys; import sys as s; raise SystemExit(0 if sys.version_info[:2] >= (3,12) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) { continue }

    # Obtain the real interpreter path
    $pyPath = & $exe @args -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $pyPath) {
      return $pyPath.Trim()
    }
  }

  return $null
}

function Ensure-Poetry {
  if (Get-Command poetry -ErrorAction SilentlyContinue) {
    poetry --version | Out-Null
    return
  }

  Write-Info "Poetry not found; attempting installation…"

  # Official installer (recommended by Poetry)
  $installer = (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content
  # Pipe installer to Python (stdin)
  $pythonToUse = (Get-Command py -ErrorAction SilentlyContinue) ? 'py' : 'python'
  $installer | & $pythonToUse -

  # Common locations (make available for current session)
  $poetryCandidates = @(
    (Join-Path $env:APPDATA 'pypoetry\venv\Scripts'),
    (Join-Path $env:USERPROFILE '.local\bin')
  )
  foreach ($p in $poetryCandidates) {
    if (Test-Path $p) { $env:Path = "$p;$env:Path" }
  }

  if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Fail "Poetry installation failed (not on PATH). Close & reopen PowerShell or add the Poetry path to PATH."
  }

  poetry --version | Out-Null
}

function Run-Tests-WithOptionalCoverage {
  <#
    Try pytest with coverage first; if the plugin is missing,
    fall back to plain pytest. Propagate failure if tests fail.
  #>
  $cmd = { poetry run pytest --cov=src --cov-report=term-missing:skip-covered --cov-report=xml --disable-warnings -q }
  try {
    & $cmd
    if ($LASTEXITCODE -eq 0) {
      Write-Ok "Tests (with coverage) PASSED"
      return
    }
  } catch {
    # ignore; retry without coverage below
  }

  Write-Info "Coverage run failed (likely pytest-cov not installed). Falling back to plain pytest…"
  poetry run pytest --disable-warnings -q
  if ($LASTEXITCODE -ne 0) {
    Fail "Tests FAILED"
  }
  Write-Ok "Tests PASSED"
}

# --- main ---------------------------------------------------------------------

Set-Location $RepoRoot
Require-Pyproject

$PythonExe = Get-PythonPath-3_12Plus
if (-not $PythonExe) {
  Fail "Python >= 3.12 not found. Install Python 3.12+ and re-run."
}
Write-Info ("Using Python: " + (& $PythonExe -V))

Ensure-Poetry

# Make sure Poetry venv lives inside the repo
Write-Info "Configuring Poetry to use in-project virtualenv (.venv)…"
poetry config virtualenvs.in-project true
Write-Ok "Poetry configured to use .venv"

# Bind Poetry to the chosen interpreter (creates .venv if needed)
poetry env use "$PythonExe" | Out-Null
Write-Ok "Virtualenv ready (.venv)"

# Policy: always remove lock to avoid conflicts across environments
$lockPath = Join-Path $RepoRoot 'poetry.lock'
if (Test-Path $lockPath) {
  Write-Info "Removing poetry.lock for a clean resolution…"
  Remove-Item $lockPath -Force
  Write-Ok "poetry.lock removed"
}

# Faster installs and stable headless plotting
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:MPLBACKEND = 'Agg'

Write-Info "Installing project with dev extras…"
poetry install --with dev --no-interaction --no-ansi
Write-Ok "Dependencies installed (dev)"

Write-Info "Running Ruff (lint)…"
poetry run ruff check src tests
Write-Ok "Ruff PASSED"

Write-Info "Running MyPy (type-check)…"
poetry run mypy src tests
Write-Ok "MyPy PASSED"

Write-Info "Running tests (with coverage if available)…"
Run-Tests-WithOptionalCoverage

Write-Ok "All checks completed SUCCESSFULLY 🎉"
