# Run tests with coverage ONLY (no XML, no durations), showing pytest’s usual summary.
# It also overrides any configured addopts (e.g. durations/xml) via `-o addopts=`.
#
# Usage:
# bash scripts/run_tests.sh 
set -Eeuo pipefail

# Pick test paths
if [[ $# -ge 1 ]]; then
  TEST_PATHS=("$@")
else
  TEST_PATHS=(tests)
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_PREFIX=""
if command -v poetry >/dev/null 2>&1 && [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
  RUN_PREFIX="poetry run"
fi

# Headless backend if plots are generated during tests
export MPLBACKEND="${MPLBACKEND:-Agg}"

cd "$REPO_ROOT"

# Run pytest with coverage summary in terminal, no xml, no durations,
# and wipe any addopts coming from config files.
$RUN_PREFIX pytest \
  -o addopts= \
  --cov=src \
  --cov-report=term \
  --disable-warnings \
  -q \
  "${TEST_PATHS[@]}"
