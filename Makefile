.PHONY: install check

BREW           := $(shell command -v brew 2>/dev/null)
NODE_MIN_MAJOR := 18
REQUIRED       := python3 node git jq gh corepack

install: _ensure_brew
	@echo "==> Installing dependencies for agentic-workflow-foundation-kit (macOS)"
	@for cmd in $(REQUIRED); do \
		if command -v $$cmd >/dev/null 2>&1; then \
			echo "  ✓ $$cmd already installed ($$($$cmd --version 2>&1 | head -1))"; \
		elif [ "$$cmd" = "corepack" ]; then \
			if ! command -v npm >/dev/null 2>&1; then \
				echo "  ✗ npm is required to install corepack"; \
				exit 1; \
			fi; \
			echo "  → Installing corepack via npm ..."; \
			npm install --global corepack; \
		else \
			echo "  → Installing $$cmd ..."; \
			brew install $$cmd; \
		fi; \
	done
	@node_major=$$(node -p 'Number(process.versions.node.split(".")[0])'); \
	if [ "$$node_major" -lt "$(NODE_MIN_MAJOR)" ]; then \
		echo "  ✗ node requires Node.js $(NODE_MIN_MAJOR)+ (found $$(node -p 'process.versions.node'))"; \
		exit 1; \
	fi; \
	corepack_version=$$(corepack --version 2>&1) || { \
		echo "  ✗ corepack --version failed: $$corepack_version"; \
		exit 1; \
	}; \
	echo "  ✓ node major   Node.js $$(node -p 'process.versions.node')"; \
	echo "  ✓ corepack    $$corepack_version"
	@echo ""
	@echo "==> All dependencies installed. Run 'make check' to verify."

check:
	@echo "==> Checking dependencies"
	@all_ok=true; \
	for cmd in $(REQUIRED); do \
		if command -v $$cmd >/dev/null 2>&1; then \
			if version=$$($$cmd --version 2>&1); then \
				printf "  ✓ %-10s %s\n" "$$cmd" "$$(printf '%s\n' "$$version" | head -1)"; \
			else \
				printf "  ✗ %-10s --version failed\n" "$$cmd"; \
				all_ok=false; \
			fi; \
		else \
			printf "  ✗ %-10s missing\n" "$$cmd"; \
			all_ok=false; \
		fi; \
	done; \
	if command -v node >/dev/null 2>&1; then \
		node_version=$$(node -p 'process.versions.node'); \
		node_major=$$(node -p 'Number(process.versions.node.split(".")[0])'); \
		if [ "$$node_major" -lt "$(NODE_MIN_MAJOR)" ]; then \
			printf "  ✗ %-10s requires Node.js %s+ (found %s)\n" "node-major" "$(NODE_MIN_MAJOR)" "$$node_version"; \
			all_ok=false; \
		else \
			printf "  ✓ %-10s Node.js %s\n" "node-major" "$$node_version"; \
		fi; \
	fi; \
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
