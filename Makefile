# JML Engine Makefile
# Common development and deployment tasks

.PHONY: help install install-dev test test-cov test-integration lint format type-check clean build docs serve deploy health-check audit

# Default target
help: ## Show this help message
	@echo "JML Engine Development Tasks"
	@echo "============================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: ## Install development dependencies
	pip install -r requirements.txt
	pip install -e ".[dev]"

# Testing
test: ## Run unit tests
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest tests/ --cov=jml_engine --cov-report=html --cov-report=term-missing

test-integration: ## Run integration tests
	pytest tests/ -m integration --tb=short

test-all: ## Run all tests
	pytest tests/ --cov=jml_engine --cov-report=html --cov-report=xml

# Code Quality
lint: ## Run linting checks
	ruff check jml_engine/
	ruff check tests/

format: ## Format code
	ruff format jml_engine/
	ruff format tests/
	ruff check --fix jml_engine/
	ruff check --fix tests/

type-check: ## Run type checking
	mypy jml_engine/

quality: lint format type-check ## Run all code quality checks

# Security
security-scan: ## Run security scanning
	bandit -r jml_engine/ -f json -o security-report.json
	safety check --output json > safety-report.json

# Development
serve: ## Start the API server
	python -m jml_engine.api.server

serve-dashboard: ## Start the dashboard
	streamlit run jml_engine/dashboard/app.py

serve-all: ## Start API and dashboard
	@echo "Starting API server..."
	@python -m jml_engine.api.server &
	@echo "Starting dashboard..."
	@streamlit run jml_engine/dashboard/app.py

dev-setup: ## Setup development environment
	pre-commit install
	pre-commit run --all-files

# Deployment
build: ## Build distribution packages
	python -m build

docker-build: ## Build Docker images
	docker-compose build

docker-up: ## Start Docker services
	docker-compose up -d

docker-down: ## Stop Docker services
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f

deploy: docker-build docker-up ## Full deployment

# Health & Monitoring
health-check: ## Run health checks
	python scripts/health_check.py

audit: ## Run security audit
	python scripts/health_check.py --audit

# Documentation
docs-build: ## Build documentation
	mkdocs build

docs-serve: ## Serve documentation locally
	mkdocs serve

# Cleanup
clean: ## Clean up temporary files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name "*.pyd" -delete
	find . -name ".coverage" -delete
	find . -name "coverage.xml" -delete

clean-all: clean ## Clean everything including dist and audit data
	rm -rf dist/
	rm -rf build/
	rm -rf audit/
	rm -rf data/
	rm -rf *.egg-info/

# CI/CD Simulation
ci: quality test-cov security-scan ## Run CI pipeline locally

# Utility
count-lines: ## Count lines of code
	find jml_engine/ -name "*.py" -exec wc -l {} + | tail -1

deps-update: ## Update dependencies
	pip install --upgrade pip-tools
	pip-compile --upgrade requirements.in
	pip-compile --upgrade requirements-dev.in

# Development workflows
new-feature: ## Start a new feature (usage: make new-feature name=feature-name)
	@if [ -z "$(name)" ]; then echo "Usage: make new-feature name=feature-name"; exit 1; fi
	git checkout -b feature/$(name)
	@echo "Created branch feature/$(name)"

release-prep: ## Prepare for release
	@echo "Running pre-release checks..."
	@make quality
	@make test-all
	@make security-scan
	@echo "✅ Pre-release checks passed"

release: release-prep ## Create a release
	@echo "Creating release..."
	@make build
	@echo "📦 Release packages built in dist/"
	@echo "🚀 Ready for release!"

# Help for common tasks
setup: install-dev dev-setup ## Complete development setup
	@echo "🎉 Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  make serve          # Start API server"
	@echo "  make test           # Run tests"
	@echo "  make quality        # Check code quality"

# Emergency
stop-all: ## Stop all running services
	pkill -f "uvicorn|streamlit|python.*server"
	docker-compose down --remove-orphans
