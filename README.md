## How to Start the Backend with Docker (Development)

To spin up the backend and its supporting services in development mode:

1. **Install & run Docker** on your machine.
2. **Clone** the repository and `cd` into its root.
3. Execute:

   ```bash
   bash ./scripts/init-docker-dev.sh
   ```

   This will launch:

   * A **PostgreSQL** container
   * A **Backend** container that mounts your local `src/` folder with live-reload

---

## Development Architecture & Philosophy

We split responsibilities between Docker-managed services and local workflows:

### 🐳 Docker-Compose Dev

* **Containers** host external services (PostgreSQL) and run the FastAPI app.
* Your **local `src/` directory** is mounted into the backend container for hot-reload.
* **No tests, migrations, linting, or type checks** run inside these containers during development.

**Why?**

* **Fater feedback** on code changes
* **Full IDE support** (debugging, autocomplete, refactoring)
* **Speed**—no rebuilding images on every change

---

### Local Quality & Testing Workflow

All code quality tools, migrations, and tests execute on your host machine:

| Task                  | Command                                  | Notes                                             |
| --------------------- | ---------------------------------------- | ------------------------------------------------- |
| **Lint & format**     | `poetry run ruff check src tests`        | Style and best-practice validations               |
| **Type checking**     | `poetry run mypy src tests`              | Static type enforcement                           |
| **Unit tests**        | `poetry run pytest -m "not integration"` | Fast, isolated tests—no DB required               |
| **Integration tests** | `poetry run pytest -m integration`       | Real-DB tests against Docker’s PostgreSQL         |
| **DB migrations**     | `poetry run alembic upgrade head`        | Applies migrations to your local Docker-hosted DB |

> **Rationale:**
> Running tests or Alembic migrations inside Docker images would force you to mount the full source tree, install dev dependencies in each build, and copy over configs—**slowing down** your feedback loop and **limiting** IDE features.

---

## CI/CD with GitHub Actions

We maintain two jobs on the `develop` branch:

### 🔍 Quick (on Pull Requests)

* Ruff & MyPy
* Unit tests only
* **No database** 

### 🛠️ Full (on pushes to `develop`)

* All **Quick** checks
* Start a **PostgreSQL** service container
* Run **Alembic** migrations
* Execute **unit + integration** tests
* Build the **Docker** image
* **Smoke-test** the `/health` endpoint

> **Guarantee:** Every commit in `develop` is style-checked, type-safe, DB-tested, and Docker-ready.

---

## Summary

1. **Docker-Compose** for services & hot-reload of the app code
2. **Local** execution of migrations, tests, and QA for speed and IDE integration
3. **CI pipeline** split into quick PR checks and full develop-branch validation




