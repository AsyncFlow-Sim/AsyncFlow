# Lint & format with Ruff (applies --fix) and type-check with MyPy.
# Usage:
#   .\scripts\quality_check.ps1

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Ruff (lint + auto-fix)
poetry run ruff check src tests --fix

# MyPy (type-check)
poetry run mypy src tests

Write-Host "✅ Linting and type-checking completed SUCCESSFULLY"
