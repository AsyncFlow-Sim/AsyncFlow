#!/usr/bin/env bash
set -euo pipefail

# Lint & format with ruff, automatic corrections applied (--fix)
poetry run ruff check src tests --fix

# Type‐check with mypy
poetry run mypy src tests

echo "✅ Linting e type‐checking completed SUCCESSFULLY"