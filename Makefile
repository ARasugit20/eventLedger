.PHONY: up down test migrate logs analytics-apply

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

analytics-apply:
	psql $$DATABASE_URL -f analytics/views.sql

test:
	USE_EXTERNAL_SERVICES=1 pytest -v

test-containers:
	pytest -v

logs:
	docker compose logs -f api worker
