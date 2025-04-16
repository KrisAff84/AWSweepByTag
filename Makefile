lint:
	poetry run black .
	poetry run mypy --explicit-package-bases .
	poetry run ruff check . --fix

run:
	PYTHONPATH=src python src/awsweepbytag/main.py