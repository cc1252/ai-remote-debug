[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^wss?://')]
    [string]$RelayWs,

    [string]$Token = $env:ARD_API_TOKEN
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $scriptDir 'agent.py'
$bakedPath = Join-Path $scriptDir '_agent_baked.py'
$buildDir = Join-Path $scriptDir 'build\customer'
$releaseDir = Join-Path $scriptDir 'release'
$venvPython = Join-Path $scriptDir '.build-venv\Scripts\python.exe'

if ([string]::IsNullOrWhiteSpace($Token) -or $Token.Length -lt 32) {
    throw '请先通过 ARD_API_TOKEN 设置至少 32 个字符的 Relay token。'
}

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = $pythonCommand.Source
}

$source = [IO.File]::ReadAllText($sourcePath)
$relayLiteral = ConvertTo-Json $RelayWs -Compress
$tokenLiteral = ConvertTo-Json $Token -Compress
$baked = $source.Replace(
    'DEFAULT_RELAY_WS = "ws://127.0.0.1:8000/ws/mobile"',
    "DEFAULT_RELAY_WS = $relayLiteral"
).Replace(
    'DEFAULT_TOKEN = ""',
    "DEFAULT_TOKEN = $tokenLiteral"
)

if ($baked -eq $source) {
    throw '没有找到可注入的默认连接参数，请检查 agent.py。'
}

New-Item -ItemType Directory -Force -Path $buildDir, $releaseDir | Out-Null

try {
    [IO.File]::WriteAllText($bakedPath, $baked, [Text.UTF8Encoding]::new($false))

    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name ard-host-agent `
        --console `
        --hidden-import websockets `
        --distpath $releaseDir `
        --workpath (Join-Path $buildDir 'work') `
        --specpath $buildDir `
        $bakedPath

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }

    Write-Host ''
    Write-Host "构建完成：$(Join-Path $releaseDir 'ard-host-agent.exe')"
    Write-Host '客户电脑只需双击这个 EXE，无需 Python 或配置文件。'
} finally {
    Remove-Item -LiteralPath $bakedPath -Force -ErrorAction SilentlyContinue
}
