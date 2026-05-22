.PHONY: up down test migrate logs

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

test:
	USE_EXTERNAL_SERVICES=1 pytest -v

test-containers:
	pytest -v

logs:
	docker compose logs -f api worker
