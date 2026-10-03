# Dev shortcuts. Assumes `python3 -m venv backend/.venv` and `npm install` in frontend/ have been done.
PY=backend/.venv/bin/python

api:        ## API on :8000 (auto-reload)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
web:        ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev
build:      ## Build the React app; the API then serves it at :8000
	cd frontend && npm run build
test:
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm test && npm run typecheck
refresh:    ## Run the projection pipeline from the command line
	cd backend && .venv/bin/python -m app.cli
