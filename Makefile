# Makefile for SmartDownloader

.PHONY: help test coverage-html clean

help:
	@echo "Available commands:"
	@echo "  make test           - Run all unit and integration tests."
	@echo "  make coverage-html  - Run tests and generate an HTML coverage report in htmlcov/."
	@echo "  make clean          - Clean up Python cache files and test artifacts."

test:
	@echo "Running unit and integration tests..."
	pytest -m "not e2e" -v

coverage-html:
	@echo "Generating HTML coverage report..."
	pytest --cov=core --cov=web --cov-branch --cov-report=html

clean:
	@echo "Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache .coverage coverage.xml htmlcov