param(
    [string]$VersionName = ("windows-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $RootDir "dist"
$WorkDir = Join-Path $RootDir "build\\pyinstaller"
$StandaloneDir = Join-Path $DistDir "windows"
$IconPng = Join-Path $RootDir "frontend\\app_icon_round.png"
$IconIco = Join-Path $DistDir "A3Agent-windows.ico"
$LocalDepsDir = Join-Path $RootDir ".pydeps"

New-Item -ItemType Directory -Force -Path $DistDir, $WorkDir, $StandaloneDir | Out-Null

$env:PYINSTALLER_CONFIG_DIR = Join-Path $WorkDir "pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null
if (Test-Path $LocalDepsDir) {
    $env:PYTHONPATH = $LocalDepsDir
}

python -c "from PIL import Image; img = Image.open(r'$IconPng'); img.save(r'$IconIco', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

if (Test-Path (Join-Path $StandaloneDir "A3Agent")) {
    Remove-Item -LiteralPath (Join-Path $StandaloneDir "A3Agent") -Recurse -Force
}

if (Test-Path (Join-Path $StandaloneDir "A3Agent.exe")) {
    Remove-Item -LiteralPath (Join-Path $StandaloneDir "A3Agent.exe") -Force
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name "A3Agent" `
  --distpath $StandaloneDir `
  --workpath $WorkDir `
  --specpath $WorkDir `
  --icon $IconIco `
  --add-data "$RootDir\\frontend;frontend" `
  --add-data "$RootDir\\assets;assets" `
  --add-data "$RootDir\\memory;memory" `
  --add-data "$RootDir\\frontends;frontends" `
  --add-data "$RootDir\\plugins;plugins" `
  --add-data "$RootDir\\reflect;reflect" `
  --add-data "$RootDir\\api_server.py;." `
  --add-data "$RootDir\\agentmain.py;." `
  --add-data "$RootDir\\agent_loop.py;." `
  --add-data "$RootDir\\ga.py;." `
  --add-data "$RootDir\\llmcore.py;." `
  --add-data "$RootDir\\path_utils.py;." `
  --add-data "$RootDir\\simphtml.py;." `
  --hidden-import "uvicorn.loops.auto" `
  --hidden-import "uvicorn.protocols.http.auto" `
  --hidden-import "uvicorn.protocols.websockets.auto" `
  --hidden-import "uvicorn.lifespan.on" `
  --hidden-import "anyio._backends._asyncio" `
  --hidden-import "PIL.ImageTk" `
  --hidden-import "PIL.ImageSequence" `
  --hidden-import "reflect.autonomous" `
  --hidden-import "reflect.scheduler" `
  launch_windows.py

$ZipPath = Join-Path $DistDir ("A3Agent-" + $VersionName + "-windows.zip")
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $StandaloneDir "A3Agent\\*") -DestinationPath $ZipPath

Write-Output (Join-Path $StandaloneDir "A3Agent")
Write-Output $ZipPath
