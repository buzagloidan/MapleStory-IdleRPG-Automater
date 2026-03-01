@echo off
echo Starting MapleStory Idle Bot...
echo Logs will be saved under project folder: logs\bot_YYYYMMDD_HHMMSS.log
echo.

REM Check if virtual environment exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python main.py %*

if errorlevel 1 (
    echo.
    echo Bot exited with an error.
    pause
)

