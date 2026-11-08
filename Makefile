.PHONY: test typecheck dev-mock up up-mock down

# Python test suites (no API key needed)
test:
	cd seraph && uv run pytest -q
	cd registry && uv run pytest -q
	cd ifc && uv run pytest -q

# TypeScript checks for the web apps
typecheck:
	cd dashboard && npx next typegen && npm run typecheck
	cd talkie && npx next typegen && npm run typecheck

# Command post on the fixtures, no external call
dev-mock:
	cd dashboard && npm run dev:mock

# Whole backend in containers (docker-compose.yml)
up:
	docker compose up --build -d

up-mock:
	MOCK=1 docker compose up --build -d

down:
	docker compose down
