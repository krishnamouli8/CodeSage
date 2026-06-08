.PHONY: install up down test index

install:
	pip install -e ".[dev]"

up:
	docker-compose up -d

down:
	docker-compose down

test:
	pytest tests/

index:
	python -m indexer.walker $(path)
