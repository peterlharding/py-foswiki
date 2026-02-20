
# -----------------------------------------------------------------------------
# PyFoswiki — top-level Makefile
# Run targets from WSL:  make run   /   make start   /   make stop
# -----------------------------------------------------------------------------

HOST       := 127.0.0.1
API_PORT   := 8621
WEB_PORT   := 8121
LOG_LEVEL  := info
VENV       := .venv
PYTHON     := $(VENV)/bin/python
UVICORN    := $(VENV)/bin/uvicorn
API_LOG    := /tmp/pyfoswiki-api.log
WEB_LOG    := /tmp/pyfoswiki-web.log
API_PID    := /tmp/pyfoswiki-api.pid
WEB_PID    := /tmp/pyfoswiki-web.pid


# -----------------------------------------------------------------------------
# API server  (port $(API_PORT))
# -----------------------------------------------------------------------------

start-api:
	PYTHONPATH=. $(UVICORN) --host $(HOST) --port $(API_PORT) app.main:app --reload

start-api-bg:
	@rm -f $(API_LOG)
	@PYTHONPATH=. nohup $(UVICORN) --host $(HOST) --port $(API_PORT) app.main:app --reload \
		> $(API_LOG) 2>&1 & \
	echo $$! > $(API_PID); \
	echo "API started (PID $$(cat $(API_PID))) — logs: $(API_LOG)"

stop-api:
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		kill $$(cat $(API_PID)) && rm -f $(API_PID) && echo "API stopped"; \
	else echo "API not running"; rm -f $(API_PID); fi

logs-api:
	@tail -f $(API_LOG)


# -----------------------------------------------------------------------------
# Web UI server  (port $(WEB_PORT))
# -----------------------------------------------------------------------------

start-web:
	PYTHONPATH=. $(UVICORN) --host $(HOST) --port $(WEB_PORT) webui.app:app --reload

start-web-bg:
	@rm -f $(WEB_LOG)
	@PYTHONPATH=. nohup $(UVICORN) --host $(HOST) --port $(WEB_PORT) webui.app:app --reload \
		> $(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID); \
	echo "Web UI started (PID $$(cat $(WEB_PID))) — logs: $(WEB_LOG)"

stop-web:
	@if [ -f $(WEB_PID) ] && kill -0 $$(cat $(WEB_PID)) 2>/dev/null; then \
		kill $$(cat $(WEB_PID)) && rm -f $(WEB_PID) && echo "Web UI stopped"; \
	else echo "Web UI not running"; rm -f $(WEB_PID); fi

logs-web:
	@tail -f $(WEB_LOG)


# -----------------------------------------------------------------------------
# Both together
# -----------------------------------------------------------------------------

start: start-api-bg start-web-bg
stop:  stop-api stop-web
status:
	@echo -n "API: "; [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null \
		&& echo "running (PID $$(cat $(API_PID)))" || echo "not running"
	@echo -n "Web: "; [ -f $(WEB_PID) ] && kill -0 $$(cat $(WEB_PID)) 2>/dev/null \
		&& echo "running (PID $$(cat $(WEB_PID)))" || echo "not running"


# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

migrate:
	PYTHONPATH=. $(VENV)/bin/alembic upgrade head

downgrade:
	PYTHONPATH=. $(VENV)/bin/alembic downgrade -1

revision:
	PYTHONPATH=. $(VENV)/bin/alembic revision --autogenerate -m "$(msg)"


# -----------------------------------------------------------------------------
# Testing
# -----------------------------------------------------------------------------

test:
	PYTHONPATH=. $(VENV)/bin/pytest tests/ -v

test-phase1:
	PYTHONPATH=. $(VENV)/bin/pytest tests/test_phase1.py -v

test-phase2:
	PYTHONPATH=. $(VENV)/bin/pytest tests/test_phase2.py -v


# -----------------------------------------------------------------------------
# User admin management
# Usage:
#   make make-admin user=alice
#   make revoke-admin user=alice
#   make bootstrap-admin user=admin   # first-time: promotes via direct SQL (no token needed)
# -----------------------------------------------------------------------------

API_URL := http://$(HOST):$(API_PORT)/api/v1

make-admin:
	@test -n "$(user)" || (echo "Usage: make make-admin user=<username>"; exit 1)
	@test -n "$(token)" || (echo "Usage: make make-admin user=<username> token=<bearer-token>"; exit 1)
	@curl -s -X PATCH $(API_URL)/auth/users/$(user)/make-admin \
		-H "Authorization: Bearer $(token)" | python3 -m json.tool

revoke-admin:
	@test -n "$(user)" || (echo "Usage: make revoke-admin user=<username>"; exit 1)
	@test -n "$(token)" || (echo "Usage: make revoke-admin user=<username> token=<bearer-token>"; exit 1)
	@curl -s -X PATCH $(API_URL)/auth/users/$(user)/revoke-admin \
		-H "Authorization: Bearer $(token)" | python3 -m json.tool

bootstrap-admin:
	@test -n "$(user)" || (echo "Usage: make bootstrap-admin user=<username>"; exit 1)
	@psql -h 127.0.0.1 -p 5432 -U pyfoswiki -d pyfoswiki \
		-c "UPDATE users SET is_admin = TRUE WHERE username = '$(user)';" \
		-c "SELECT username, is_admin FROM users WHERE username = '$(user)';"


# -----------------------------------------------------------------------------
# Housekeeping
# -----------------------------------------------------------------------------

install:
	$(VENV)/bin/pip install -r requirements.txt

.PHONY: start-api start-api-bg stop-api logs-api \
        start-web start-web-bg stop-web logs-web \
        start stop status \
        migrate downgrade revision \
        test test-phase1 test-phase2 install \
        make-admin revoke-admin bootstrap-admin
