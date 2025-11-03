@echo off
REM IMPORTANT!
REM This file starts the bot inside venv, but only for running it as a service in production.
REM For development and testing, execute with "python .\main.py" command.

REM Change directory to the app root (where main.py and venv are located)
cd C:\mt5-python-bot

REM Activate the virtual environment
call .\venv\Scripts\activate.bat

REM Run the main Python script using the venv's python.exe
python .\main.py

REM Deactivate (optional, but good practice)
deactivate
