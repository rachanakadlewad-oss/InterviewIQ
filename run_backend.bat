@echo off
call .venv\Scripts\activate.bat
python -m uvicorn app.api.main:app_factory --factory --host 127.0.0.1 --port 8000
