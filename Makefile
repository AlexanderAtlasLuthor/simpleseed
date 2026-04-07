.PHONY: up down build logs shell-api setup

## Start all services (build if needed)
up:
	docker compose up -d --build

## Stop and remove containers
down:
	docker compose down

## Build images without starting
build:
	docker compose build

## Tail logs (all services); use `make logs s=api` to filter
logs:
	docker compose logs -f $(s)

## Open a shell in the API container
shell-api:
	docker compose exec api bash

## First-time setup: copy env template if .env doesn't exist
setup:
	@if [ ! -f backend/.env ]; then \
		cp backend/.env.example backend/.env 2>/dev/null || \
		echo "ANTHROPIC_API_KEY=\nDATABASE_URL=postgresql+asyncpg://simpleseed:simpleseed@db:5432/simpleseed\nLLM_MODEL=claude-haiku-4-5-20251001" > backend/.env; \
		echo "Created backend/.env — set your ANTHROPIC_API_KEY before running 'make up'"; \
	else \
		echo "backend/.env already exists"; \
	fi
