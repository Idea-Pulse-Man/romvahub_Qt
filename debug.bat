@echo off
rem romva hub, DEBUG version: this black window shows every server call, every
rem error and the Resume Maker's log. Everything is also saved to
rem %APPDATA%\RomvaHub\debug.log  (send that file when something goes wrong).
rem Close the normal romva hub first (tray icon -> Quit): only one can run.
cd /d "%~dp0"
python -c "import PySide6, httpx, keyring" 2>nul || python -m pip install -r requirements.txt
python main.py --debug %*
echo.
echo romva hub closed. Log file: %APPDATA%\RomvaHub\debug.log
pause
