@echo off
REM Installs all dependencies for the libertad-politica-vault RAG pipeline.
REM Requires Python 3.13 or earlier (LlamaIndex uses pydantic v1, incompatible with 3.14+).

setlocal

set VENV_DIR=.venv

REM --- Locate Python ---
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYTHON=py -3.13
) else (
    set PYTHON=python
)

echo Using Python: %PYTHON%
%PYTHON% --version
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.13 or earlier.
    exit /b 1
)

REM --- Create venv if missing ---
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment in %VENV_DIR%...
    %PYTHON% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo Virtual environment already exists at %VENV_DIR%.
)

REM --- Activate ---
call "%VENV_DIR%\Scripts\activate.bat"

REM --- Upgrade pip tooling ---
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    exit /b 1
)

REM --- Install requirements ---
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    exit /b 1
)

echo.
echo ========================================
echo   Installation complete.
echo   Activate the venv with:
echo     %VENV_DIR%\Scripts\activate.bat
echo ========================================
endlocal
