@echo off
setlocal

set "ROOT=C:\Users\admin\Downloads\puzzle"
set "CONDA_ENV=puzzle-ai"
set "LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1"
set "LLM_MODEL=qwen-flash"
set "LLM_MAX_TOKENS=3000"
set "LLM_TEMPERATURE=0.2"
set "CONDA_BAT="
set "AI_BACKEND_CMD="

if "%DASHSCOPE_API_KEY%"=="" (
  echo [WARN] DASHSCOPE_API_KEY is not set in the current environment.
  echo        Please set it first with:
  echo        setx DASHSCOPE_API_KEY "your_key"
  echo        Then reopen this terminal and run this script again.
  echo.
)

if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" (
  set "AI_BACKEND_CMD=cd /d %ROOT% && set LLM_BASE_URL=%LLM_BASE_URL% && set LLM_MODEL=%LLM_MODEL% && set LLM_MAX_TOKENS=%LLM_MAX_TOKENS% && set LLM_TEMPERATURE=%LLM_TEMPERATURE% && ""%CONDA_PREFIX%\python.exe"" -m uvicorn backend.main:app --host 127.0.0.1 --port 8011 --reload"
)

if not defined AI_BACKEND_CMD (
  for %%P in (
    "%UserProfile%\anaconda3\condabin\conda.bat"
    "%UserProfile%\miniconda3\condabin\conda.bat"
    "%ProgramData%\anaconda3\condabin\conda.bat"
    "%ProgramData%\miniconda3\condabin\conda.bat"
  ) do (
    if not defined CONDA_BAT if exist "%%~fP" set "CONDA_BAT=%%~fP"
  )
)

if not defined AI_BACKEND_CMD if defined CONDA_BAT (
  set "AI_BACKEND_CMD=cd /d %ROOT% && call ""%CONDA_BAT%"" activate %CONDA_ENV% && set LLM_BASE_URL=%LLM_BASE_URL% && set LLM_MODEL=%LLM_MODEL% && set LLM_MAX_TOKENS=%LLM_MAX_TOKENS% && set LLM_TEMPERATURE=%LLM_TEMPERATURE% && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011 --reload"
)

start "Puzzle V1 Web" cmd /k "cd /d %ROOT% && node serve-v1-local.mjs"
start "Puzzle V1 Bridge" cmd /k "cd /d %ROOT%\v1\node-bridge && node server.mjs"

if defined AI_BACKEND_CMD (
  start "Puzzle V1 AI Backend" cmd /k "%AI_BACKEND_CMD%"
) else (
  echo [ERROR] Could not locate a usable conda python runtime.
  echo         Recommended: open Anaconda PowerShell Prompt, activate %CONDA_ENV%, then run this script.
  echo         Fallback: edit this file so CONDA_ENV or conda.bat path matches your local setup.
  echo.
)

echo Puzzle V1 AI services are starting...
echo Page:      http://127.0.0.1:8000/v1/index.html
echo Bridge:    http://127.0.0.1:3210/health
echo AI Backend:http://127.0.0.1:8011/health
echo.
echo Recommended flow:
echo 1. Open Anaconda PowerShell Prompt
echo 2. Run: conda activate %CONDA_ENV%
echo 3. Run this script
echo.
echo If the AI window does not start:
echo 1. confirm the env is activated before launching this script
echo 2. check that %%CONDA_PREFIX%% points to the expected env
echo 3. edit CONDA_ENV in this file if your env has a different name
echo 4. make sure DASHSCOPE_API_KEY is set

endlocal
