<#
.SYNOPSIS  ImageAudit development helper (Windows PowerShell).
.EXAMPLE   .\scripts\dev.ps1 setup | api | web | test | lint | demo | build-exe
.NOTES     Works with any Python >= 3.11 (3.11, 3.12, ...). `build-exe` produces dist\ImageAudit.exe.
#>
param(
  [Parameter(Position = 0)][ValidateSet("setup", "api", "web", "test", "lint", "demo", "build-exe", "help")][string]$Command = "help",
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$VPy = Join-Path $Venv "Scripts\python.exe"

function Find-Python {
  foreach ($cand in @(@("py", "-3"), @("python"), @("python3"))) {
    if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
      $args2 = @($cand | Select-Object -Skip 1) + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
      $v = & $cand[0] @args2 2>$null
      if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.11") { return , $cand }
    }
  }
  throw "Python 3.11 or newer was not found on PATH."
}
function Invoke-Checked { param([string]$Exe, [string[]]$A) & $Exe @A; if ($LASTEXITCODE -ne 0) { throw "$Exe $($A -join ' ') failed ($LASTEXITCODE)" } }

switch ($Command) {
  "setup" {
    if (-not (Test-Path $VPy)) { $p = Find-Python; $pa = @($p | Select-Object -Skip 1) + @("-m", "venv", $Venv); Invoke-Checked $p[0] $pa }
    Invoke-Checked $VPy @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $VPy @("-m", "pip", "install", "-e", ((Join-Path $Root "backend") + "[api,dev]"))
    Push-Location (Join-Path $Root "frontend"); try { Invoke-Checked "npm" @("install") } finally { Pop-Location }
  }
  "api"  { Invoke-Checked $VPy @("-m", "imageaudit", "serve", "--reload") }
  "web"  { Push-Location (Join-Path $Root "frontend"); try { Invoke-Checked "npm" @("run", "dev") } finally { Pop-Location } }
  "test" { Push-Location (Join-Path $Root "backend"); try { Invoke-Checked $VPy @("-m", "pytest", "-q") } finally { Pop-Location } }
  "lint" {
    Push-Location (Join-Path $Root "backend"); try { Invoke-Checked $VPy @("-m", "ruff", "check", ".") } finally { Pop-Location }
    Push-Location (Join-Path $Root "frontend"); try { Invoke-Checked "npm" @("run", "lint"); Invoke-Checked "npm" @("run", "typecheck") } finally { Pop-Location }
  }
  "demo" {
    $dest = Join-Path $Root "build\demo-dataset"
    if (-not (Test-Path $dest)) { Invoke-Checked $VPy @("-m", "imageaudit", "demo", $dest) }
    Invoke-Checked $VPy @("-m", "imageaudit", "scan", $dest)
  }
  "build-exe" {
    $build = Join-Path $Root "packaging\build_exe.ps1"
    if ($Rest -contains "-SkipSmoke") { & $build -SkipSmoke } else { & $build }
  }
  default { Get-Help $PSCommandPath }
}
