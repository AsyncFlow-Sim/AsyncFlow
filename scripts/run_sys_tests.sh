# Run only system tests (marked @pytest.mark.system) with the required env var.
# Keeps output concise (no XML, no slowest list), shows the usual pytest summary.
#
# Usage:
#   bash scripts/run_system_tests.sh 
#
# Notes:
# - Uses `poetry run` when Poetry + pyproject.toml are present; otherwise falls back to `pytest`.
# - Forces a headless backend for any plots generated during tests.

set -Eeuo pipefail

# Pick test paths (default to tests/system)
if [[ $# -ge 1 ]]; then
  TEST_PATHS=("$@")
else
  TEST_PATHS=(tests/system)
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_PREFIX=""
if command -v poetry >/dev/null 2>&1 && [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
  RUN_PREFIX="poetry run"
fi

# Headless plotting; enable system tests
export MPLBACKEND="${MPLBACKEND:-Agg}"
export ASYNCFLOW_RUN_SYSTEM_TESTS=1

cd "$REPO_ROOT"

echo "==> Running system tests…"
# Clear any configured addopts and run only system-marked tests
# Keep output short but with the final summary line.
$RUN_PREFIX pytest \
  -o addopts= \
  -m system \
  --disable-warnings \
  -q \
  "${TEST_PATHS[@]}"

echo "✅ System tests PASSED"
