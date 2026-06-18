# setup.ps1 — 在目标电脑上一键安装运行环境（便携版 Python + 依赖 + ffmpeg）
# 不需要管理员权限，不污染系统，全部装在本文件夹内。
$ErrorActionPreference = "Stop"
# 脚本在 packaging\ 下，包根目录是其上一级（runtime/ffmpeg/requirements 都装在包根）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$root = Split-Path -Parent $scriptDir
Set-Location $root
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$PY_DIR     = Join-Path $root "runtime\python"
$PY_EXE     = Join-Path $PY_DIR "python.exe"
$FF_DIR     = Join-Path $root "ffmpeg\bin"
$FF_EXE     = Join-Path $FF_DIR "ffmpeg.exe"
$REQ        = Join-Path $root "requirements.txt"
# 国内 PyPI 镜像（清华），大幅加速依赖下载；如在海外可改成 https://pypi.org/simple
$PIP_INDEX  = "https://pypi.tuna.tsinghua.edu.cn/simple"

function Info($m) { Write-Host "  $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  $m" -ForegroundColor Green }

# ===== 1/3 便携版 Python =====
if (Test-Path $PY_EXE) {
    Ok "[1/3] Python 已存在，跳过。"
} else {
    Info "[1/3] 下载便携版 Python（约 30MB，来自 GitHub，国内可能较慢）..."
    $api = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    $rel = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "ai-analysis-setup" }
    $asset = $null
    foreach ($ver in @("3.12.", "3.13.", "3.11.")) {
        $asset = $rel.assets | Where-Object {
            $_.name -like "cpython-$ver*-x86_64-pc-windows-msvc-install_only.tar.gz"
        } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw "未找到合适的便携版 Python 资源。" }
    $tgz = Join-Path $root "_python.tar.gz"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tgz -UseBasicParsing
    New-Item -ItemType Directory -Force -Path (Join-Path $root "runtime") | Out-Null
    # Windows 10+ 自带 tar；install_only 包解压后顶层为 python\
    tar -xf $tgz -C (Join-Path $root "runtime")
    Remove-Item $tgz -Force
    if (-not (Test-Path $PY_EXE)) { throw "Python 解压后未找到 python.exe。" }
    Ok "      Python 安装完成。"
}

# ===== 2/3 Python 依赖 =====
Info "[2/3] 安装 Python 依赖（用清华镜像加速）..."
& $PY_EXE -m pip install --upgrade pip -i $PIP_INDEX --no-warn-script-location
& $PY_EXE -m pip install -r $REQ -i $PIP_INDEX --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败（错误码 $LASTEXITCODE）。" }
Ok "      依赖安装完成。"

# ===== 3/3 ffmpeg（录像抽帧用）=====
if (Test-Path $FF_EXE) {
    Ok "[3/3] ffmpeg 已存在，跳过。"
} else {
    Info "[3/3] 下载 ffmpeg（录像抽帧用，约 90MB）..."
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
    if (-not (Test-Path $FF_EXE)) { throw "ffmpeg 解压后未找到 ffmpeg.exe。" }
    Ok "      ffmpeg 安装完成。"
}

# 写入安装标记
"installed $(Get-Date -Format o)" | Out-File -FilePath (Join-Path $root ".installed") -Encoding utf8
Write-Host ""
Ok "全部安装完成！双击「启动.bat」即可使用。"
