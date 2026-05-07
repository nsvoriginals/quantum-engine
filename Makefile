.PHONY: install dev test test-unit run run-prod docker-build docker-up docker-down

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v

test-unit:
	pytest tests/ -v -m "not integration"

run:
	uvicorn api.endpoints:app --host 0.0.0.0 --port 8001 --reload

run-prod:
	gunicorn api.endpoints:app -c gunicorn.conf.py

docker-build:
	docker build -t auditsmart-quantum:latest .

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
