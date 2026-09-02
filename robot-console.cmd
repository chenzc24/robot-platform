@echo off
setlocal
set "ROBOT_ROOT=%~dp0"
set "PYTHONPATH=%ROBOT_ROOT%src\console"
"%ROBOT_ROOT%.venv\Scripts\python.exe" -m web_console --open %*
