clean:
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@rm -rf .mypy_cache .ruff_cache

format:
	poetry run ruff check . --fix
	poetry run black .

lint:
	poetry run black .
	poetry run mypy --explicit-package-bases .
	poetry run ruff check .

run:
	@PYTHONPATH=src python src/awsweepbytag/main.py

test:
	@poetry run pytest -W ignore::DeprecationWarning -srP

test-debug: # To see all logs from tests
	@LOG_LEVEL=DEBUG poetry run pytest -W ignore::DeprecationWarning -srP