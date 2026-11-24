@echo off
rem romva hub: install what is missing, then start the app without a console window.
cd /d "%~dp0"
python -c "import PySide6, httpx, keyring" 2>nul || python -m pip install -r requirements.txt
start "" pythonw main.py %*
