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
