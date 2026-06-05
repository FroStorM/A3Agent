param(
    [string]$VersionName = ("windows-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$AppVersion = "0.1.0",
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistAppDir = Join-Path $RootDir "dist\windows\A3Agent"
$ReleaseDir = Join-Path $RootDir "release"
$IssPath = Join-Path $RootDir "installer\A3Agent.iss"
$OutputBase = "A3Agent-Setup-$VersionName"

if (-not (Test-Path (Join-Path $DistAppDir "A3Agent.exe"))) {
    throw "Missing packaged app at $DistAppDir. Run build_windows_standalone.ps1 first."
}

if (-not (Test-Path $IssPath)) {
    throw "Missing installer script: $IssPath"
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

if (-not $IsccPath) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $IsccPath = $cmd.Source
    }
}

if (-not $IsccPath) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $IsccPath = $candidate
            break
        }
    }
}

if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
    throw "ISCC.exe not found. Install Inno Setup 6, then rerun this script."
}

$env:A3AGENT_VERSION = $AppVersion
$env:A3AGENT_SOURCE_DIR = $DistAppDir
$env:A3AGENT_OUTPUT_DIR = $ReleaseDir
$env:A3AGENT_OUTPUT_BASE = $OutputBase

& $IsccPath $IssPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$InstallerPath = Join-Path $ReleaseDir "$OutputBase.exe"
if (-not (Test-Path $InstallerPath)) {
    throw "Installer was not created: $InstallerPath"
}

Write-Output $InstallerPath
