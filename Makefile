# Makefile for development tasks

UV ?= uv
IMAGE ?= pdf-usage:latest

.PHONY: help install dev test fmt lint clean build deploy docker-build docker-run

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(UV) sync --all-extras

dev: ## Start development server
	$(UV) run uvicorn app:app --reload --host 0.0.0.0 --port 8000

test: ## Run tests
	$(UV) run pytest -v --cov=. --cov-report=term-missing --cov-report=html

test-fast: ## Run tests without coverage
	$(UV) run pytest -v

fmt: ## Format code
	$(UV) run black . --line-length=120
	$(UV) run isort . --profile=black --line-length=120
	$(UV) run ruff format .

lint: ## Lint code
	$(UV) run ruff check . --fix
	$(UV) run black . --check --line-length=120
	$(UV) run isort . --check-only --profile=black --line-length=120

clean: ## Clean build artifacts
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: ## Build the package
	$(UV) build

deploy-check: ## Check deployment readiness
	@echo "Checking deployment readiness..."
	@echo "✓ vercel.json exists: $$(test -f vercel.json && echo "Yes" || echo "No")"
	@echo "✓ api/index.py exists: $$(test -f api/index.py && echo "Yes" || echo "No")"
	@echo "✓ .env.example exists: $$(test -f .env.example && echo "Yes" || echo "No")"
	@echo "✓ Tests pass: $$($(UV) run pytest --tb=no -q && echo "Yes" || echo "No")"

pre-commit-install: ## Install pre-commit hooks
	$(UV) run pre-commit install

pre-commit-run: ## Run pre-commit on all files
	$(UV) run pre-commit run --all-files

setup-dev: install pre-commit-install ## Setup development environment
	@echo "Development environment setup complete!"
	@echo "Run 'make dev' to start the development server"

# Docker targets
docker-build: ## Build Docker image
	docker build -t $(IMAGE) .

docker-run: ## Run Docker container
	docker run --rm -p 8080:8080 --env-file .env.example $(IMAGE)

# Vercel deployment helpers
vercel-dev: ## Start Vercel development server
	vercel dev

vercel-deploy: ## Deploy to Vercel
	vercel --prod
