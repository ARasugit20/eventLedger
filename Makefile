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
	pytest -v --tb=short

test-cov:
	pytest -v --cov=app --cov-report=term-missing --cov-fail-under=75

test-containers:
	pytest -v

logs:
	docker compose logs -f api worker
