@echo off
setlocal
set "ROBOT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%ROBOT_PYTHON%" (
  echo ROBOT_CLI_ERROR virtual_environment_missing 1>&2
  echo ACTION Run: py -3.12 -m venv .venv 1>&2
  exit /b 2
)
"%ROBOT_PYTHON%" "%~dp0tools\robot_cli.py" %*
exit /b %ERRORLEVEL%
