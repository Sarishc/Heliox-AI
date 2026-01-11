# Heliox-AI Development Makefile

.PHONY: help start stop restart logs build clean test migrate migration lint format demo test-golden-path

help: ## Show this help message
	@echo "Heliox-AI Development Commands"
	@echo "==============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

start: ## Start all services
	@echo "🚀 Starting services..."
	docker-compose up -d
	@echo "✅ Services started. Visit http://localhost:8000/docs"

stop: ## Stop all services
	@echo "🛑 Stopping services..."
	docker-compose down
	@echo "✅ Services stopped"

restart: stop start ## Restart all services

logs: ## Show API logs (follow mode)
	docker-compose logs -f api

logs-all: ## Show all service logs (follow mode)
	docker-compose logs -f

build: ## Build Docker images
	docker-compose build

rebuild: ## Rebuild Docker images from scratch
	docker-compose build --no-cache

clean: ## Remove all containers, volumes, and networks
	@echo "🧹 Cleaning up..."
	docker-compose down -v
	@echo "✅ Cleanup complete"

ps: ## Show running services
	docker-compose ps

shell: ## Open a shell in the API container
	docker-compose exec api /bin/bash

db-shell: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U heliox -d heliox_db

redis-shell: ## Open Redis CLI
	docker-compose exec redis redis-cli

migration: ## Create a new database migration (usage: make migration MSG="your message")
	docker-compose exec api alembic revision --autogenerate -m "$(MSG)"

migrate: ## Apply database migrations
	docker-compose exec api alembic upgrade head

migrate-down: ## Rollback last migration
	docker-compose exec api alembic downgrade -1

migrate-history: ## Show migration history
	docker-compose exec api alembic history --verbose

test: ## Run tests
	docker-compose exec api pytest

test-cov: ## Run tests with coverage
	docker-compose exec api pytest --cov=app --cov-report=html

lint: ## Run linter
	docker-compose exec api ruff check app

format: ## Format code
	docker-compose exec api black app

check: lint test ## Run linter and tests

dev-setup: ## Setup development environment
	@echo "🔧 Setting up development environment..."
	@if [ ! -f backend/.env ]; then \
		cp backend/.env.example backend/.env; \
		echo "✅ Created .env file"; \
	else \
		echo "⚠️  .env file already exists"; \
	fi
	@echo "✅ Development environment ready"
	@echo "Run 'make start' to start services"

health: ## Check service health
	@echo "🏥 Checking service health..."
	@curl -s http://localhost:8000/health | python -m json.tool
	@echo ""
	@curl -s http://localhost:8000/health/db | python -m json.tool

status: ps health ## Show status of all services

install-local: ## Install dependencies locally (for IDE support)
	cd backend && pip install -r requirements.txt

# Docker-free local development
local-start: ## Start only databases (for local Python development)
	docker-compose up -d postgres redis

local-run: ## Run API locally (requires Python 3.11 and venv)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

demo: ## Setup and start demo environment (starts Docker, runs migrations, seeds data)
	@bash scripts/demo.sh

test-golden-path: ## Run end-to-end Golden Path test (verifies critical demo path)
	@bash scripts/test-golden-path.sh

