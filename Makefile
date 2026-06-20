.PHONY: install check

BREW     := $(shell command -v brew 2>/dev/null)
REQUIRED := python3 git jq gh

install: _ensure_brew
	@echo "==> Installing dependencies for agentic-workflow-foundation-kit (macOS)"
	@for cmd in $(REQUIRED); do \
		if command -v $$cmd >/dev/null 2>&1; then \
			echo "  ✓ $$cmd already installed ($$($$cmd --version 2>&1 | head -1))"; \
		else \
			echo "  → Installing $$cmd ..."; \
			brew install $$cmd; \
		fi; \
	done
	@echo ""
	@echo "==> All dependencies installed. Run 'make check' to verify."

check:
	@echo "==> Checking dependencies"
	@all_ok=true; \
	for cmd in $(REQUIRED); do \
		if command -v $$cmd >/dev/null 2>&1; then \
			printf "  ✓ %-10s %s\n" "$$cmd" "$$($$cmd --version 2>&1 | head -1)"; \
		else \
			printf "  ✗ %-10s missing\n" "$$cmd"; \
			all_ok=false; \
		fi; \
	done; \
	if $$all_ok; then \
		echo ""; echo "All OK."; \
	else \
		echo ""; echo "Some dependencies are missing. Run 'make install' to fix."; \
		exit 1; \
	fi

_ensure_brew:
ifndef BREW
	$(error Homebrew が見つかりません。https://brew.sh からインストールしてください)
endif
