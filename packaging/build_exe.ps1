<#
.SYNOPSIS  Build dist\ImageAudit.exe (single file) from this source tree, then smoke-test it.
.PARAMETER SkipSmoke  Do not launch the produced EXE afterwards (not recommended).
.NOTES     Windows only (PyInstaller cannot cross-compile). Does not modify any source file:
           intermediate output goes to build\ and frontend\.next-export (git-ignored).
#>
param([switch]$SkipSmoke)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
function Run { param([string]$Exe, [string[]]$A) & $Exe @A; if ($LASTEXITCODE -ne 0) { throw "$Exe $($A -join ' ') failed ($LASTEXITCODE)" } }

Write-Host "==> Validating prerequisites"
if ($env:OS -ne "Windows_NT") { throw "build-exe must run on Windows (it produces a Windows .exe)." }
if (-not (Test-Path $VPy)) { throw "No .venv found. Run: .\scripts\dev.ps1 setup" }
Run $VPy @("-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'")
foreach ($tool in "node", "npm") { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found on PATH (needed at BUILD time only)." } }
Run $VPy @("-m", "pip", "install", "--quiet", "pyinstaller>=6.6", "-e", ((Join-Path $Root "backend") + "[api]"))

Write-Host "==> Building the frontend (static export, same-origin API)"
Push-Location (Join-Path $Root "frontend")
try {
  if (-not (Test-Path "node_modules\next")) { Run "npm" @("ci") }
  # NEXT_EXPORT=1 selects the static export AND forces same-origin API calls (see next.config.mjs).
  # Do not use an empty NEXT_PUBLIC_API_URL for this: PowerShell deletes variables set to "".
  $env:NEXT_EXPORT = "1"; $env:NEXT_PUBLIC_SAME_ORIGIN = "1"; $env:NEXT_TELEMETRY_DISABLED = "1"
  Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
  if (Test-Path ".next-export") { Remove-Item ".next-export" -Recurse -Force }
  Run "npm" @("run", "build")
} finally { Remove-Item Env:NEXT_EXPORT, Env:NEXT_PUBLIC_SAME_ORIGIN -ErrorAction SilentlyContinue; Pop-Location }
$bad = Get-ChildItem (Join-Path $Root "frontend\.next-export") -Recurse -Include *.js,*.html | Select-String -SimpleMatch "127.0.0.1:8000" -List
if ($bad) { throw "Packaged frontend still references 127.0.0.1:8000: $($bad.Path -join ', ')" }

Write-Host "==> Packaging with PyInstaller (onefile)"
$dist = Join-Path $Root "dist"
Run $VPy @("-m", "PyInstaller", (Join-Path $Root "packaging\imageaudit.spec"), "--noconfirm", "--clean",
           "--distpath", $dist, "--workpath", (Join-Path $Root "build\pyinstaller"))
$exe = Join-Path $dist "ImageAudit.exe"
if (-not (Test-Path $exe)) { throw "Build finished but $exe was not produced." }
Write-Host ("Built {0} ({1:N1} MB)" -f $exe, ((Get-Item $exe).Length / 1MB))

if (-not $SkipSmoke) {
  Write-Host "==> Smoke-testing the real EXE (scan, reports, delete, restart, persistence)"
  Run $VPy @((Join-Path $Root "packaging\smoke_test.py"), $exe, "--dataset", (Join-Path $Root "examples\sample_dataset"))
}
Write-Host "Done: $exe"
