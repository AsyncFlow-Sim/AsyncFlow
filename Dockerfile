# ─────────────── Build stage ───────────────
FROM python:3.12-slim AS builder

# Install system dependencies for psycopg and build tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

# Copy only pyproject.toml, poetry.lock, README so we leverage cache
COPY pyproject.toml poetry.lock* README.md ./

# Install Poetry (into /root/.local/bin)
RUN curl -sSL https://install.python-poetry.org | python3 -

# Symlink Poetry into /usr/local/bin so "poetry" is on PATH
RUN ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Tell Poetry not to create its own venv
RUN poetry config virtualenvs.create false

# Install only the prod deps (uvicorn, fastapi, sqlalchemy, psycopg...)
RUN poetry install --no-root --without dev

# Now copy in your application code
COPY src/ ./src

# ─────────── Runtime stage ───────────
FROM python:3.12-slim AS runtime

WORKDIR /opt/app

# 1) Copy installed libraries
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12

# 2) Copy console scripts (uvicorn, alembic, etc.)
COPY --from=builder /usr/local/bin /usr/local/bin

# 3) Copy application code
COPY --from=builder /opt/app/src ./src

# 4) Non-root user
RUN adduser --disabled-password --gecos '' appuser
USER appuser

WORKDIR /opt/app/src

# 5) Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
