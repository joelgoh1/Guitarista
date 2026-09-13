.PHONY: setup dev api web ml test lint gen-api clean

setup:
	corepack enable && pnpm install
	cd apps/api && uv sync --all-extras
	cd apps/ml && uv sync
	cp -n .env.example .env || true
	cp -n .env.example apps/api/.env || true

dev:
	pnpm dev

api:
	cd apps/api && uv run guitarista-api

web:
	pnpm --filter web dev

ml-separate:
	cd apps/ml && uv sync --extra separate

test:
	pnpm test
	cd apps/api && uv run pytest -q

lint:
	pnpm lint
	cd apps/api && uv run ruff check . && uv run mypy src

gen-api:
	pnpm gen:api

clean:
	rm -rf node_modules apps/*/node_modules packages/*/node_modules apps/web/.next .turbo
