# make_package.ps1 — 把 ai_analysis 组装成可分发的便携包（不含运行时，目标机首次 install 时下载）
# 在源机器（本机）运行：powershell -ExecutionPolicy Bypass -File packaging\make_package.ps1
$ErrorActionPreference = "Stop"
$pkgDir = Split-Path -Parent $MyInvocation.MyCommand.Definition   # ...\ai_analysis\packaging
$src    = Split-Path -Parent $pkgDir                              # ...\ai_analysis
$stage  = Join-Path $src "_dist\ai_analysis_portable"
$zipOut = Join-Path $src "_dist\ai_analysis_portable.zip"

Write-Host "组装便携包到 $stage" -ForegroundColor Cyan
if (Test-Path (Join-Path $src "_dist")) { Remove-Item (Join-Path $src "_dist") -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$stage\app" | Out-Null

# ---- 1. 复制程序源码（排除数据、缓存、构建产物、密钥之外的东西）----
$includeFiles = @(
    "aggregate.py","analysis_engine.py","app.py","benchmark.py","config.py","funnel.py",
    "insight_analyze.py","llm.py","orchestrator.py","prompts.py","store.py",
    "time_analysis.py","video_analyze.py","zmeng_api.py",
    "config.example.json","README.md"
)
foreach ($f in $includeFiles) {
    $p = Join-Path $src $f
    if (Test-Path $p) { Copy-Item $p -Destination "$stage\app\$f" -Force }
}
# pages 目录（多页面）
Copy-Item (Join-Path $src "pages") -Destination "$stage\app\pages" -Recurse -Force
# assets（若有内容）
if (Test-Path (Join-Path $src "assets")) {
    Copy-Item (Join-Path $src "assets") -Destination "$stage\app\assets" -Recurse -Force
}
# 端口探测辅助脚本（qidong.bat 调用，放到 app/ 下）
Copy-Item (Join-Path $pkgDir "find_port.py") -Destination "$stage\app\find_port.py" -Force

# ---- 2. config.json：带上你的密钥一起打包（按需求「配置一起打包」）----
$cfg = Join-Path $src "config.json"
if (Test-Path $cfg) {
    Copy-Item $cfg -Destination "$stage\app\config.json" -Force
    Write-Host "  已打包 config.json（含 API 密钥）" -ForegroundColor Yellow
} else {
    Copy-Item (Join-Path $src "config.example.json") -Destination "$stage\app\config.json" -Force
}

# ---- 3. 空的 data 目录骨架（程序会自建，这里给个占位）----
foreach ($d in @("data\rooms","data\analyses","data\videos")) {
    New-Item -ItemType Directory -Force -Path "$stage\app\$d" | Out-Null
}

# ---- 4. 安装/启动脚本 + 依赖清单 ----
New-Item -ItemType Directory -Force -Path "$stage\packaging" | Out-Null
Copy-Item (Join-Path $pkgDir "setup.ps1")  -Destination "$stage\packaging\setup.ps1" -Force
Copy-Item (Join-Path $pkgDir "install.bat") -Destination "$stage\install.bat" -Force
Copy-Item (Join-Path $pkgDir "qidong.bat")  -Destination "$stage\qidong.bat" -Force
Copy-Item (Join-Path $pkgDir "requirements.portable.txt") -Destination "$stage\requirements.txt" -Force
if (Test-Path (Join-Path $pkgDir "部署说明.md")) {
    Copy-Item (Join-Path $pkgDir "部署说明.md") -Destination "$stage\部署说明.md" -Force
}

# ---- 5. 打 zip ----
Write-Host "压缩为 $zipOut" -ForegroundColor Cyan
Compress-Archive -Path $stage -DestinationPath $zipOut -Force

Write-Host ""
Write-Host "完成！分发这个文件：" -ForegroundColor Green
Write-Host "  $zipOut"
Write-Host "目标电脑：解压 -> 双击 install.bat（联网，一次）-> 双击 qidong.bat" -ForegroundColor Green
