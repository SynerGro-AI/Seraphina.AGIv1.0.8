<#
.SYNOPSIS
  Seraphina.AGI + Glyph - one-shot Windows installer.

.DESCRIPTION
  Quick install (PowerShell):
    iex (irm https://raw.githubusercontent.com/SynerGro-AI/Seraphina.AGIv1.0.8/main/install.ps1)

  Or from a local clone:
    git clone https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git
    cd Seraphina.AGIv1.0.8
    .\install.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoUrl,
    [string]$RepoBranch,
    [string]$InstallDir,
    [switch]$SystemInstall
)
$ErrorActionPreference = 'Stop'

if (-not $RepoUrl)    { $RepoUrl    = if ($env:SERAPHINA_REPO_URL)    { $env:SERAPHINA_REPO_URL }    else { 'https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git' } }
if (-not $RepoBranch) { $RepoBranch = if ($env:SERAPHINA_REPO_BRANCH) { $env:SERAPHINA_REPO_BRANCH } else { 'main' } }
if (-not $InstallDir) { $InstallDir = if ($env:SERAPHINA_INSTALL_DIR) { $env:SERAPHINA_INSTALL_DIR } else { Join-Path $env:USERPROFILE '.seraphina-src' } }

function Say  { param($m) Write-Host "[seraphina] $m" -ForegroundColor Cyan }
function Warn { param($m) Write-Host "[seraphina] $m" -ForegroundColor Yellow }
function Die  { param($m) Write-Host "[seraphina] $m" -ForegroundColor Red; exit 1 }

# --- locate or clone repo ----------------------------------------------------
if ((Test-Path .\pyproject.toml) -and (Test-Path .\glyph) -and (Test-Path .\seraphina)) {
    $RepoDir = (Get-Location).Path
    Say "running from local clone: $RepoDir"
} else {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die 'git not found - install git first' }
    if (Test-Path (Join-Path $InstallDir '.git')) {
        Say "updating existing clone at $InstallDir"
        git -C $InstallDir fetch --quiet origin $RepoBranch
        git -C $InstallDir checkout --quiet $RepoBranch
        git -C $InstallDir pull --quiet --ff-only
    } else {
        Say "cloning $RepoUrl -> $InstallDir"
        git clone --quiet --depth 1 --branch $RepoBranch $RepoUrl $InstallDir
    }
    $RepoDir = $InstallDir
}
Set-Location $RepoDir

# --- locate python -----------------------------------------------------------
$Py = $env:SERAPHINA_PYTHON
if (-not $Py) {
    foreach ($c in 'python','py','python3') {
        if (Get-Command $c -ErrorAction SilentlyContinue) { $Py = $c; break }
    }
}
if (-not $Py) { Die 'Python 3.9+ not found - install from https://www.python.org/' }

$pyVer = & $Py -c "import sys;print('%d.%d'%sys.version_info[:2])"
Say "using python: $Py ($pyVer)"
& $Py -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)"
if ($LASTEXITCODE -ne 0) { Die "Python 3.9+ required (found $pyVer)" }

# --- ensure pip --------------------------------------------------------------
& $Py -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Say 'bootstrapping pip'
    & $Py -m ensurepip --upgrade *> $null
    if ($LASTEXITCODE -ne 0) { Die 'pip not available' }
}

# --- install glyph + seraphina ----------------------------------------------
$pipUser = @()
if (-not $env:VIRTUAL_ENV -and -not $SystemInstall) {
    $pipUser = @('--user')
    Say 'installing into user site (no venv detected); use -SystemInstall to override'
}

Say 'installing glyph package manager'
& $Py -m pip install @pipUser --upgrade --quiet .\glyph
if ($LASTEXITCODE -ne 0) { Die 'glyph install failed' }

Say 'installing seraphina core'
& $Py -m pip install @pipUser --upgrade --quiet .
if ($LASTEXITCODE -ne 0) { Die 'seraphina install failed' }

# --- bootstrap glyph env -----------------------------------------------------
Say 'bootstrapping glyph environment'
& $Py -m glyph bootstrap
if ($LASTEXITCODE -ne 0) { Warn 'glyph bootstrap returned non-zero (continuing)' }

# --- PATH hint ---------------------------------------------------------------
if ($pipUser) {
    $userScripts = & $Py -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"
    if ($userScripts -and ($env:Path -notlike "*$userScripts*")) {
        Warn "add this to PATH so 'seraphina' and 'glyph' are available:"
        Warn "    $userScripts"
    }
}

Write-Host ''
Write-Host '  installed.' -ForegroundColor Green
Write-Host ''
Write-Host '    seraphina            # interactive wizard'
Write-Host '    seraphina --help'
Write-Host '    python -m glyph list'
Write-Host ''
Write-Host "  source: $RepoDir"
