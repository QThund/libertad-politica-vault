# Installs all dependencies for the libertad-politica-vault RAG pipeline.
# Requires Python 3.13 or earlier (LlamaIndex uses pydantic v1, incompatible with 3.14+).

$ErrorActionPreference = "Stop"
$VenvDir = ".venv"

# --- Locate Python ---
$python = if (Get-Command py -ErrorAction SilentlyContinue) { @("py", "-3.13") } else { @("python") }
Write-Host "Using Python: $($python -join ' ')"
& $python[0] $python[1..($python.Length-1)] --version

# --- Create venv if missing ---
if (-not (Test-Path "$VenvDir\Scripts\Activate.ps1")) {
    Write-Host "Creating virtual environment in $VenvDir..."
    & $python[0] $python[1..($python.Length-1)] -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists at $VenvDir."
}

# --- Activate ---
. "$VenvDir\Scripts\Activate.ps1"

# --- Install ---
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

Write-Host ""
Write-Host "========================================"
Write-Host "  Installation complete."
Write-Host "  Activate the venv with:"
Write-Host "    $VenvDir\Scripts\Activate.ps1"
Write-Host "========================================"
