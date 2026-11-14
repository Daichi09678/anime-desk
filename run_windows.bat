@echo off
setlocal
cd /d "%~dp0"

echo [Frieren Desk] Memeriksa Python dan dependencies...
rem Prefer the verified local runtime when a newer Python has incompatible wheels.
set "PYTHON=.venv313\Scripts\python.exe"
set "PYTHONW=.venv313\Scripts\pythonw.exe"
if exist "%PYTHON%" (
    "%PYTHON%" -c "import PySide6.QtWidgets, edge_tts, mutagen; from PIL import Image" >nul 2>&1
    if not errorlevel 1 goto launch
)
set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONW=.venv\Scripts\pythonw.exe"
if exist "%PYTHON%" (
    "%PYTHON%" -c "import PySide6.QtWidgets, edge_tts, mutagen; from PIL import Image" >nul 2>&1
    if not errorlevel 1 goto launch
)

rem Reuse a working system installation before downloading another Qt runtime.
python -c "import PySide6.QtWidgets, edge_tts, mutagen; from PIL import Image" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)"') do set "PYTHON=%%P"
    goto system_ready
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Pasang Python 3.11+ dan aktifkan Add Python to PATH.
        pause
        exit /b 1
    )
)
set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONW=.venv\Scripts\pythonw.exe"
"%PYTHON%" -m ensurepip --upgrade
if errorlevel 1 goto dependency_error
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto dependency_error
goto launch

:system_ready
set "PYTHONW=%PYTHON:python.exe=pythonw.exe%"

:launch
echo [Frieren Desk] Menjalankan aplikasi...
if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%~dp0main.py" %*
) else (
    start "" "%PYTHON%" "%~dp0main.py" %*
)
exit /b 0

:dependency_error
echo [ERROR] Dependencies belum berhasil dipasang. Periksa koneksi dan coba lagi.
pause
exit /b 1
