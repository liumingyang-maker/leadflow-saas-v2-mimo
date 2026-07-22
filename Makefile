.PHONY: lint format-check test diff-check check

PYTHON ?= python

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

test:
	$(PYTHON) -m pytest

diff-check:
	git diff --check

check: lint format-check test diff-check
