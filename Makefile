.PHONY: install run shell test cov fmt lint check clean stack-up stack-down run-simple-event-example run-rpc-example

PY ?= poetry run python

install:
	$(PY) -m pip install -U pip setuptools wheel
	poetry install

run:
	poetry run kontiki-tui

shell:
	poetry shell

test:
	$(PY) -m pytest -q

fmt:
	$(PY) -m isort .
	$(PY) -m black .

lint:
	$(PY) -m flake8 . --exclude .venv,dist,build --jobs 1

check: fmt lint

clean:
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache .coverage dist build

run-simple-event-example:
	@echo "Running simple event example..."
	$(PY) -m examples.simple_example

run-rpc-example:
	@echo "Running RPC example..."
	$(PY) -m examples.rpc_example


# -----------------------------------------------------------------------------
# Docker stack (RabbitMQ + registry + services)
# -----------------------------------------------------------------------------
stack-up:
	docker compose -f docker-compose.stack.yaml up -d --build

stack-down:
	docker compose -f docker-compose.stack.yaml down
