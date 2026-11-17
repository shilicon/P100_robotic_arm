param(
    [Parameter(Mandatory=$true)][string]$AmdPython,
    [Parameter(Mandatory=$true)][string]$LanHost,
    [string]$AmdInstallation = $env:RYZEN_AI_INSTALLATION_PATH,
    [switch]$ListenLan
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if ($env:OS -ne "Windows_NT") { throw "Live deployment requires Windows." }
$AmdPython = (Resolve-Path $AmdPython).Path
if ([string]::IsNullOrWhiteSpace($AmdInstallation) -or !(Test-Path $AmdInstallation -PathType Container)) { throw "Supply -AmdInstallation for Ryzen AI 1.8.0." }
& $AmdPython -c "import sys; assert sys.version_info[:2] == (3,12), 'AMD deployment requires Python 3.12'; import onnxruntime, onnxruntime_genai; from importlib.metadata import version; assert version('onnxruntime-vitisai') == '1.27.0'; assert version('onnxruntime-genai-directml-ryzenai') == '0.14.0'"
if ($LASTEXITCODE -ne 0) { throw "Select the AMD Ryzen AI 1.8.0 environment's python.exe." }
$AmdEnvironment = (& $AmdPython -c "import sys; print(sys.prefix)").Trim()
if (Test-Path ".venv") { throw "Existing .venv preserved. Use the manual installation steps to update it." }
if (Test-Path ".venv-asr") { throw "Existing .venv-asr preserved. Use the manual installation steps to update it." }
& $AmdPython -m venv --system-site-packages .venv
if ($LASTEXITCODE -ne 0) { throw "Backend environment creation failed." }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
& $AmdPython -m venv .venv-asr
if ($LASTEXITCODE -ne 0) { throw "CPU ASR environment creation failed." }
& .\.venv-asr\Scripts\python.exe -m pip install -r requirements-asr.txt
if ($LASTEXITCODE -ne 0) { throw "ASR dependency installation failed." }
$ConfigureArguments = @("scripts/configure.py", "--lan-host", $LanHost,
    "--amd-installation", $AmdInstallation, "--amd-environment", $AmdEnvironment)
if ($ListenLan) { $ConfigureArguments += "--listen-lan" }
& .\.venv\Scripts\python.exe @ConfigureArguments
if ($LASTEXITCODE -ne 0) { throw "Configuration failed." }
Write-Output "Installed. Read docs/MODELS.md before downloading models. No service was started."
