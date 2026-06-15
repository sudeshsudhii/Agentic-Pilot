.PHONY: test-unit test-integration test-all lint format backend dev

test-unit:
	pytest tests/ -v --ignore=tests/integration

test-integration:
	INTEGRATION_TESTS=1 pytest tests/integration/ -v -s

test-all:
	pytest tests/ -v

lint:
	ruff check backend/

format:
	ruff format backend/

backend:
	python backend/main.py

dev:
	cd frontend && npm run dev
