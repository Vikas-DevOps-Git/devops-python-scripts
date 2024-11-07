.PHONY: install test lint format clean

install:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

lint:
	flake8 eks_health_check/ vault_rotation/ incident_triage/ --max-line-length=120
	pylint eks_health_check/ vault_rotation/ incident_triage/ --disable=C0114,C0115

format:
	black eks_health_check/ vault_rotation/ incident_triage/ tests/

type-check:
	mypy eks_health_check/ vault_rotation/ incident_triage/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage

# Quick smoke tests (no cluster needed)
smoke:
	python -m eks_health_check.main --help
	python -m vault_rotation.main --help
	python -m incident_triage.main --help
	python -m incident_triage.main \
		--payload '{"id":"TEST-001","title":"OOM kill on payment-api","environment":"production"}' \
		--dry-run
