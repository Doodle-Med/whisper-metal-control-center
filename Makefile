SHELL := /bin/bash
PYTHON ?= python3

.PHONY: bootstrap run clean-storage package-dmg

bootstrap:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r backend/requirements.txt
	./scripts/setup_whisper_cpp.sh

run:
	@if [ ! -d .venv ]; then $(MAKE) bootstrap; fi
	. .venv/bin/activate && python -m backend.app

clean-storage:
	rm -rf storage
	mkdir -p storage/uploads storage/jobs

package-dmg: clean-storage
	./scripts/package_dmg.sh
