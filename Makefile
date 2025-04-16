lint:
	poetry run black .
	poetry run mypy --explicit-package-bases .
	poetry run ruff check . --fix