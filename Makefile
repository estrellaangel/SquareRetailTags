.PHONY: dev build test migrate

dev:
	uvicorn esl.web.app:app --reload --port 8001 & npm --prefix frontend run dev

build:
	npm --prefix frontend run types
	npm --prefix frontend run build

test:
	pytest

migrate:
	alembic upgrade head
