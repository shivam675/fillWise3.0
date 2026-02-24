# ─────────────────────────────────────────────────────────────────────────────
# FillWise 3.0  ·  Makefile
#
# Requires: Python 3.11+, Node 20+, Docker, Docker Compose v2.
# On Windows use Git Bash or WSL to run this file.
# ─────────────────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help
SHELL         := bash

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR   := backend
FRONTEND_DIR  := frontend
VENV          := $(BACKEND_DIR)/.venv
PYTHON        := $(VENV)/bin/python
PIP           := $(VENV)/bin/pip
ALEMBIC       := $(VENV)/bin/alembic
PYTEST        := $(VENV)/bin/pytest
MYPY          := $(VENV)/bin/mypy
RUFF          := $(VENV)/bin/ruff

# Docker Compose profile (override: make up PROFILE=postgres)
PROFILE       ?=
COMPOSE_FLAGS := $(if $(PROFILE),--profile $(PROFILE),)

# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: help
help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' \
	  | sort

# ─────────────────────────────────────────────────────────────────────────────
# Environment setup
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: install
install: install-backend install-frontend  ## Install all dependencies

.PHONY: install-backend
install-backend:  ## Create venv and install Python deps
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e "$(BACKEND_DIR)[dev]"
	@echo "✓ Backend deps installed"

.PHONY: install-frontend
install-frontend:  ## Install Node deps for the frontend
	cd $(FRONTEND_DIR) && npm ci
	@echo "✓ Frontend deps installed"

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: migrate
migrate:  ## Apply Alembic migrations (upgrade head)
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

.PHONY: migrate-rollback
migrate-rollback:  ## Rollback last Alembic migration
	cd $(BACKEND_DIR) && $(ALEMBIC) downgrade -1

.PHONY: migrate-new
migrate-new:  ## Create a new Alembic migration (MSG="description")
	@test -n "$(MSG)" || (echo "Error: MSG is required.  Use: make migrate-new MSG=\"your message\"" && exit 1)
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(MSG)"

.PHONY: migrate-history
migrate-history:  ## Show Alembic migration history
	cd $(BACKEND_DIR) && $(ALEMBIC) history --verbose

.PHONY: seed
seed:  ## Seed default roles and admin user (reads env from .env)
	@echo "Seeding is handled automatically on backend startup."
	@echo "Start the backend with: make dev-backend"

# ─────────────────────────────────────────────────────────────────────────────
# Development servers
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: dev
dev:  ## Start backend + frontend in parallel (requires tmux or runs sequentially)
	$(MAKE) migrate
	$(MAKE) -j2 dev-backend dev-frontend

.PHONY: dev-backend
dev-backend:  ## Start FastAPI backend with auto-reload
	@cp -n .env.example .env 2>/dev/null || true
	cd $(BACKEND_DIR) && \
	  RELOAD=true $(PYTHON) -m uvicorn app.main:app \
	    --host 0.0.0.0 \
	    --port $${PORT:-8000} \
	    --reload \
	    --log-level $${LOG_LEVEL:-debug}

.PHONY: dev-frontend
dev-frontend:  ## Start Vite dev server with HMR
	cd $(FRONTEND_DIR) && npm run dev

# ─────────────────────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: test
test: test-backend test-frontend  ## Run full test suite

.PHONY: test-backend
test-backend:  ## Run pytest with coverage
	cd $(BACKEND_DIR) && \
	  $(PYTEST) tests/ \
	    --cov=app \
	    --cov-report=term-missing \
	    --cov-report=html:htmlcov \
	    --cov-fail-under=85 \
	    -v

.PHONY: test-frontend
test-frontend:  ## Run Vitest frontend unit tests
	cd $(FRONTEND_DIR) && npm run test:run

.PHONY: test-e2e
test-e2e:  ## Run Playwright end-to-end tests (requires running app)
	cd $(FRONTEND_DIR) && npm run test:e2e

.PHONY: test-watch
test-watch:  ## Run pytest in watch mode (requires pytest-watch)
	cd $(BACKEND_DIR) && $(VENV)/bin/ptw -- tests/ -v

# ─────────────────────────────────────────────────────────────────────────────
# Linting & type-checking
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: lint
lint: lint-backend lint-frontend  ## Run all linters

.PHONY: lint-backend
lint-backend:  ## Run Ruff linter on backend
	$(RUFF) check $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

.PHONY: lint-fix
lint-fix:  ## Auto-fix ruff linting issues
	$(RUFF) check --fix $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

.PHONY: lint-frontend
lint-frontend:  ## Run ESLint on frontend
	cd $(FRONTEND_DIR) && npm run lint

.PHONY: format
format:  ## Format backend code with Ruff formatter
	$(RUFF) format $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

.PHONY: type-check
type-check: type-check-backend type-check-frontend  ## Run type checkers

.PHONY: type-check-backend
type-check-backend:  ## Run MyPy on backend
	$(MYPY) $(BACKEND_DIR)/app --ignore-missing-imports

.PHONY: type-check-frontend
type-check-frontend:  ## Run tsc --noEmit on frontend
	cd $(FRONTEND_DIR) && npm run type-check

# Combined quality gate
.PHONY: check
check: lint type-check test-backend  ## Run lint + type check + tests (CI quality gate)

# ─────────────────────────────────────────────────────────────────────────────
# Docker
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: build
build:  ## Build Docker images (backend + frontend)
	docker compose $(COMPOSE_FLAGS) build

.PHONY: up
up:  ## Start all containers (add PROFILE=postgres to use PostgreSQL)
	docker compose $(COMPOSE_FLAGS) up -d
	@echo "✓ Services started.  Backend: http://localhost:$${PORT:-8000}"

.PHONY: down
down:  ## Stop and remove containers (keeps volumes)
	docker compose $(COMPOSE_FLAGS) down

.PHONY: down-volumes
down-volumes:  ## Stop containers and remove ALL volumes (DESTROYS DATA)
	docker compose $(COMPOSE_FLAGS) down -v

.PHONY: logs
logs:  ## Tail logs from all containers
	docker compose $(COMPOSE_FLAGS) logs -f

.PHONY: logs-backend
logs-backend:  ## Tail backend container logs
	docker compose $(COMPOSE_FLAGS) logs -f backend

.PHONY: ps
ps:  ## Show running containers
	docker compose $(COMPOSE_FLAGS) ps

.PHONY: restart
restart:  ## Restart all containers
	docker compose $(COMPOSE_FLAGS) restart

.PHONY: shell
shell:  ## Open a bash shell in the running backend container
	docker compose exec backend bash

# ─────────────────────────────────────────────────────────────────────────────
# Ollama model management
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: ollama-pull
ollama-pull:  ## Pull the configured model from Ollama registry
	ollama pull $${OLLAMA_MODEL:-ministral:3b}

.PHONY: ollama-list
ollama-list:  ## List locally available Ollama models
	ollama list

.PHONY: ollama-health
ollama-health:  ## Check Ollama API health
	curl -sf http://$${OLLAMA_BASE_URL:-localhost:11434}/api/tags | python3 -m json.tool

# ─────────────────────────────────────────────────────────────────────────────
# Misc utilities
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: env-copy
env-copy:  ## Copy .env.example to .env (safe, will not overwrite)
	@test -f .env && echo ".env already exists — skipping." || (cp .env.example .env && echo "✓ .env created from .env.example. Edit it before starting the app.")

.PHONY: clean
clean:  ## Remove build artefacts, __pycache__, .coverage
	find $(BACKEND_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -name "*.pyc" -delete 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/.mypy_cache \
	       $(BACKEND_DIR)/.ruff_cache \
	       $(BACKEND_DIR)/.pytest_cache \
	       $(BACKEND_DIR)/htmlcov \
	       $(BACKEND_DIR)/.coverage \
	       $(FRONTEND_DIR)/dist \
	       $(FRONTEND_DIR)/node_modules/.vite
	@echo "✓ Cleaned"

.PHONY: clean-all
clean-all: clean  ## Also remove venv and node_modules (full reset)
	rm -rf $(VENV) $(FRONTEND_DIR)/node_modules
	@echo "✓ Full clean done.  Run: make install"

.PHONY: open-api
open-api:  ## Open Swagger UI in default browser
	python3 -m webbrowser "http://localhost:$${PORT:-8000}/docs"
