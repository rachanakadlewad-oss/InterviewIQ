@echo off
setlocal
where py >nul 2>nul || (echo Python launcher "py" not found. Install Python 3.10-3.12 from python.org and tick "Add to PATH". & exit /b 1)
if not exist .venv ( py -3 -m venv .venv || exit /b 1 )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || exit /b 1
if not exist .env copy .env.example .env
python data\generate_demo_data.py
echo.
echo Setup complete. Next: run_backend.bat (terminal 1) and run_frontend.bat (terminal 2).
