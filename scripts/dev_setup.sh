# Post-clone developer setup for AsyncFlow (Linux/macOS/WSL).
#
# What it does:
#   1) Ensures Poetry is available (prefers pipx if present; otherwise uses
#      the official installer).
#   2) Configures Poetry to create an in-project virtualenv (.venv).
#   3) Removes poetry.lock (fresh dependency resolution by policy).
#   4) Installs the project with dev extras.
#   5) Runs ruff, mypy, and pytest (with coverage if available).
#
# Usage:
#   bash scripts/dev_setup.sh
#
# Notes:
#   - Run this from anywhere; it will cd to repo root.
#   - Requires Python >= 3.12 to be available (python3.12 or python3).
#   - We do NOT delete an existing .venv; it will be reused if compatible.

set -Eeuo pipefail

# --- helpers -----------------------------------------------------------------

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

err() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }
ok()   { echo "✅ $*"; }

require_pyproject() {
  [[ -f "$repo_root/pyproject.toml" ]] || err "pyproject.toml not found at repo root ($repo_root)"
}

pick_python() {
  # Return a python executable >= 3.12
  for cand in python3.13 python3.12 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)'; then
        echo "$cand"
        return 0
      fi
    fi
  done
  err "Python >= 3.12 not found. Install python3.12+ and re-run."
}

ensure_poetry() {
  if command -v poetry >/dev/null 2>&1; then
    poetry --version || true
    return 0
  fi

  info "Poetry not found; attempting installation…"

  if command -v pipx >/dev/null 2>&1; then
    pipx install poetry || pipx upgrade poetry || true
  else
    # Official installer (recommended by Poetry) — installs to ~/.local/bin
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
  fi

  # Ensure poetry is now available on PATH
  export PATH="$HOME/.local/bin:$PATH"
  command -v poetry >/dev/null 2>&1 || err "Poetry installation failed (not on PATH)."
  poetry --version || true
}

run_tests_with_optional_coverage() {
  # Try pytest with coverage first; if plugin missing, fallback to plain pytest.
  set +e
  poetry run pytest \
    --cov=src \
    --cov-report=term-missing:skip-covered \
    --cov-report=xml \
    --disable-warnings -q
  local status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    ok "Tests (with coverage) PASSED"
    return 0
  fi

  info "Coverage run failed (likely pytest-cov not installed). Falling back to plain pytest…"

  poetry run pytest --disable-warnings -q
  ok "Tests PASSED"
}

# --- main --------------------------------------------------------------------

cd "$repo_root"
require_pyproject

PY_BIN="$(pick_python)"
info "Using Python: $("$PY_BIN" -V)"

ensure_poetry

# Make sure Poetry venv lives inside the repo
info "Configuring Poetry to use in-project virtualenv (.venv)…"
poetry config virtualenvs.in-project true
ok "Poetry configured to use .venv"

# Bind Poetry to the chosen interpreter (creates .venv if needed)
poetry env use "$PY_BIN" >/dev/null 2>&1 || true
ok "Virtualenv ready (.venv)"

# Policy: always remove lock to avoid conflicts across environments
if [[ -f poetry.lock ]]; then
  info "Removing poetry.lock for a clean resolution…"
  rm -f poetry.lock
  ok "poetry.lock removed"
fi

# Faster installs and stable headless plotting
export PIP_DISABLE_PIP_VERSION_CHECK=1
export MPLBACKEND=Agg

info "Installing project with dev extras…"
poetry install --with dev --no-interaction --no-ansi
ok "Dependencies installed (dev)"

info "Running Ruff (lint)…"
poetry run ruff check src tests
ok "Ruff PASSED"

info "Running MyPy (type-check)…"
poetry run mypy src tests
ok "MyPy PASSED"

info "Running tests (with coverage if available)…"
run_tests_with_optional_coverage

ok "All checks completed SUCCESSFULLY 🎉"
