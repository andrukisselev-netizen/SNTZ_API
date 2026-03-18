@echo off
cd /d "%~dp0"
timeout /t 1 /nobreak >nul
REM Если python не в PATH — замените строку ниже на полный путь, например:
REM "C:\ComfyUI\python_embeded\python.exe" trigger_comfyui.py
python trigger_comfyui.py --prompt-file="%CD%\ps_prompt.txt"
if %ERRORLEVEL% neq 0 pause
