# setup.ps1 - one-shot installer (portable Python + deps + ffmpeg), all inside this folder.
$ErrorActionPreference = "Stop"
# script sits in packaging\ ; package root is one level up (runtime/ffmpeg/requirements live there)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$root = Split-Path -Parent $scriptDir
Set-Location $root
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$PY_DIR     = Join-Path $root "runtime\python"
$PY_EXE     = Join-Path $PY_DIR "python.exe"
$FF_DIR     = Join-Path $root "ffmpeg\bin"
$FF_EXE     = Join-Path $FF_DIR "ffmpeg.exe"
$REQ        = Join-Path $root "requirements.txt"
# Tsinghua PyPI mirror speeds up downloads in China; outside CN switch to https://pypi.org/simple
$PIP_INDEX  = "https://pypi.tuna.tsinghua.edu.cn/simple"

function Info($m) { Write-Host "  $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  $m" -ForegroundColor Green }

# ===== 1/3 portable Python =====
if (Test-Path $PY_EXE) {
    Ok "[1/3] Python already present, skipping."
} else {
    Info "[1/3] Downloading portable Python (~30MB from GitHub)..."
    $api = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    $rel = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "ai-analysis-setup" }
    $asset = $null
    foreach ($ver in @("3.12.", "3.13.", "3.11.")) {
        $asset = $rel.assets | Where-Object {
            $_.name -like "cpython-$ver*-x86_64-pc-windows-msvc-install_only.tar.gz"
        } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw "No suitable portable Python asset found." }
    $tgz = Join-Path $root "_python.tar.gz"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tgz -UseBasicParsing
    New-Item -ItemType Directory -Force -Path (Join-Path $root "runtime") | Out-Null
    # Windows 10+ ships tar; install_only archive extracts to top-level python\
    tar -xf $tgz -C (Join-Path $root "runtime")
    Remove-Item $tgz -Force
    if (-not (Test-Path $PY_EXE)) { throw "python.exe not found after extraction." }
    Ok "      Python installed."
}

# ===== 2/3 Python dependencies =====
Info "[2/3] Installing Python dependencies (via mirror)..."
& $PY_EXE -m pip install --upgrade pip -i $PIP_INDEX --no-warn-script-location
& $PY_EXE -m pip install -r $REQ -i $PIP_INDEX --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed (exit $LASTEXITCODE)." }
Ok "      Dependencies installed."

# ===== 3/3 ffmpeg (video frame extraction) =====
if (Test-Path $FF_EXE) {
    Ok "[3/3] ffmpeg already present, skipping."
} else {
    Info "[3/3] Downloading ffmpeg (~90MB)..."
    $zip = Join-Path $root "_ffmpeg.zip"
    $tmp = Join-Path $root "_ffmpeg_tmp"
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path $FF_DIR | Out-Null
    foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
        $f = Get-ChildItem -Path $tmp -Recurse -Filter $name | Select-Object -First 1
        if ($f) { Copy-Item $f.FullName -Destination (Join-Path $FF_DIR $name) -Force }
    }
    Remove-Item $zip -Force
    Remove-Item $tmp -Recurse -Force
    if (-not (Test-Path $FF_EXE)) { throw "ffmpeg.exe not found after extraction." }
    Ok "      ffmpeg installed."
}

# write install marker
"installed $(Get-Date -Format o)" | Out-File -FilePath (Join-Path $root ".installed") -Encoding utf8
Write-Host ""
Ok "All done! Double-click  qidong.bat  to start."
