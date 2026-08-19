dev:
	cd backend && venv/Scripts/activate && uvicorn main:app --reload --port 8000

tunnel:
	ngrok http 8000
