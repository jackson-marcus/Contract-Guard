.PHONY: install lint format test bench api ui mlflow docker-up docker-down

install:
	uv sync --group dev

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest --cov

bench:
	uv run python scripts/make_contracts.py
	uv run python scripts/redline_bench.py

api:
	uv run uvicorn contractguard.api.main:app --reload --port 8160

ui:
	CONTRACTGUARD_API_URL=http://localhost:8160 uv run streamlit run src/contractguard/ui/app.py --server.port 8661

mlflow:
	uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5017

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
