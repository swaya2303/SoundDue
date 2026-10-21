# SoundDue — project tasks
# Run with: make demo
# On Windows without GNU make: python backend/scripts/seed_demo.py

.PHONY: demo backend frontend test help

help:
	@echo "Available targets:"
	@echo "  demo      - Seed the Midnight Train demo case and print steps"
	@echo "  backend   - Start the FastAPI server (port 8000)"
	@echo "  frontend  - Start the Vite dev server (port 5173)"
	@echo "  test      - Run the backend pytest suite"

demo:
	python backend/scripts/seed_demo.py

backend:
	cd backend && python -m uvicorn main:app --port 8000 --reload

frontend:
	cd frontend && npx vite --port 5173

test:
	cd backend && python -m pytest tests/ -q
