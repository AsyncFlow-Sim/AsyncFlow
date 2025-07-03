#!/usr/bin/env bash
# scripts/init-docker-dev.sh 
# Bring up local development stack using .env.dev in project root


set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# 0. Paths
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker_fs/docker-compose.dev.yml"
ENV_DEV="$PROJECT_ROOT/docker_fs/.env.dev"
ENV_DOT="$PROJECT_ROOT/docker_fs/.env"

# ──────────────────────────────────────────────────────────────────────────────
# 0.1 Make script executable
# ──────────────────────────────────────────────────────────────────────────────
if [[ ! -x "$SCRIPT_PATH" ]]; then
  chmod +x "$SCRIPT_PATH" || true
fi

# ──────────────────────────────────────────────────────────────────────────────
# 0.2 Ensure docker_fs/.env exists for Compose interpolation
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f "$ENV_DEV" && ! -f "$ENV_DOT" ]]; then
  echo ">>> Copying .env.dev → .env for Compose interpolation"
  cp "$ENV_DEV" "$ENV_DOT"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 1. Load env vars from .env.dev into this shell
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f "$ENV_DEV" ]]; then
  set -o allexport
  source "$ENV_DEV"
  set +o allexport
else
  echo "ERROR: $ENV_DEV not found. Please create it from .env.example." >&2
  exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# 2. Pull remote images (only missing ones)
# ──────────────────────────────────────────────────────────────────────────────
echo ">>> Pulling external service images..."
docker compose \
  --env-file "$ENV_DEV" \
  -f "$COMPOSE_FILE" pull

# ──────────────────────────────────────────────────────────────────────────────
# 3. Start Postgres + pgAdmin (detached)
# ──────────────────────────────────────────────────────────────────────────────
echo ">>> Starting Postgres and pgAdmin..."
docker compose \
  --env-file "$ENV_DEV" \
  -f "$COMPOSE_FILE" up -d db pgadmin

# ──────────────────────────────────────────────────────────────────────────────
# 4. Run Alembic migrations
# ──────────────────────────────────────────────────────────────────────────────
echo ">>> Applying database migrations (Alembic)…"
cd "$PROJECT_ROOT"
poetry run alembic upgrade head

# ──────────────────────────────────────────────────────────────────────────────
# 5. Build (if needed) & start everything in background
# ──────────────────────────────────────────────────────────────────────────────
echo ">>> Building (if needed) and starting all services…"
docker compose \
  --env-file "$ENV_DEV" \
  -f "$COMPOSE_FILE" up -d --build

echo ">>> Development stack is up!"
echo "    • Backend: http://localhost:8000"
echo "    • pgAdmin: http://localhost:8080"
echo
echo "To tail backend logs without warnings, run:"
echo "  docker compose \\
  --env-file \"$ENV_DEV\" \\
  -f \"$COMPOSE_FILE\" logs -f backend"
