[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+(?:\.\d+)?$')]
    [string]$Version = '1.0.0',
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$MainScript = Join-Path $ProjectRoot 'main.py'
$SourceRoot = Join-Path $ProjectRoot 'src'
$IconScript = Join-Path $ProjectRoot 'scripts\create_icon.py'
$IconPath = Join-Path $ProjectRoot 'packaging\TokenAnalyzer.ico'
$InnoScript = Join-Path $ProjectRoot 'packaging\TokenAnalyzer.iss'
$InnoLanguage = Join-Path $ProjectRoot 'packaging\ChineseSimplified.isl'
$BuildRoot = Join-Path $ProjectRoot 'build\windows'
$NuitkaOutput = Join-Path $BuildRoot 'nuitka'
$InstallerStage = Join-Path $BuildRoot 'installer'
$DistRoot = Join-Path $ProjectRoot 'dist'
$StandaloneTarget = Join-Path $DistRoot 'TokenAnalyzer'
$InstallerTarget = Join-Path $DistRoot 'installer'
$LockPath = Join-Path $ProjectRoot '.windows-build.lock'
$NuitkaCache = Join-Path $ProjectRoot 'build\nuitka-cache'

function Assert-PathInsideProject {
    param([Parameter(Mandatory)][string]$Path)

    $absolute = [System.IO.Path]::GetFullPath($Path)
    $prefix = $ProjectRoot.TrimEnd('\') + '\'
    if (-not $absolute.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝操作项目目录以外的路径：$absolute"
    }
}

function Remove-BuildPath {
    param([Parameter(Mandatory)][string]$Path)

    Assert-PathInsideProject -Path $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Find-InnoCompiler {
    $command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "未找到项目Python环境：$PythonExe"
}
if (-not (Test-Path -LiteralPath $MainScript)) {
    throw "未找到程序入口：$MainScript"
}

& $PythonExe -c 'import nuitka' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "缺少免费构建工具Nuitka。请先运行：.\.venv\Scripts\python.exe -m pip install -r .\packaging\requirements-build.txt"
}

& $PythonExe -c 'import PIL' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "缺少图标依赖Pillow。请先运行：.\.venv\Scripts\python.exe -m pip install -r .\packaging\requirements-build.txt"
}

$InnoCompiler = $null
if (-not $SkipInstaller) {
    $InnoCompiler = Find-InnoCompiler
    if (-not $InnoCompiler) {
        throw "未找到Inno Setup 6。它是免费工具，请从https://jrsoftware.org/isdl.php下载安装后重新运行。"
    }

    if (-not (Test-Path -LiteralPath $InnoLanguage)) {
        throw "项目缺少简体中文安装向导文件：$InnoLanguage"
    }
}

try {
    New-Item -ItemType File -Path $LockPath -ErrorAction Stop | Out-Null
} catch {
    throw "检测到另一个Windows构建任务，或上次构建异常中断。确认没有构建进程后删除：$LockPath"
}

try {
    Remove-BuildPath -Path $BuildRoot
    New-Item -ItemType Directory -Path $NuitkaOutput -Force | Out-Null
    New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $NuitkaCache -Force | Out-Null
    $env:NUITKA_CACHE_DIR = $NuitkaCache
    $PreviousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ($PreviousPythonPath) {
        $SourceRoot + [System.IO.Path]::PathSeparator + $PreviousPythonPath
    } else {
        $SourceRoot
    }

    & $PythonExe $IconScript --output $IconPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $IconPath)) {
        throw '应用图标生成失败。'
    }

    $NuitkaArgs = @(
        '-m', 'nuitka',
        '--standalone',
        '--enable-plugin=pyside6',
        '--windows-console-mode=disable',
        '--mingw64',
        '--assume-yes-for-downloads',
        "--windows-icon-from-ico=$IconPath",
        '--output-filename=TokenAnalyzer.exe',
        "--output-dir=$NuitkaOutput",
        '--include-package=token_analyzer',
        '--include-package=python_calamine',
        '--include-package=xlsxwriter',
        "--company-name=TokenAnalyzer",
        "--product-name=词元分析器",
        "--file-description=词元分析器",
        "--file-version=$Version",
        "--product-version=$Version",
        '--copyright=Copyright 2026 TokenAnalyzer',
        '--nofollow-import-to=tests',
        '--nofollow-import-to=*.tests',
        $MainScript
    )
    & $PythonExe @NuitkaArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka构建失败，退出码：$LASTEXITCODE。首次构建需要联网下载免费的MinGW编译器，请检查网络后重试。"
    }

    $BuiltDirectory = Get-ChildItem -LiteralPath $NuitkaOutput -Directory -Filter '*.dist' | Select-Object -First 1
    if ($null -eq $BuiltDirectory) {
        throw 'Nuitka未生成独立应用目录。'
    }
    $BuiltExe = Join-Path $BuiltDirectory.FullName 'TokenAnalyzer.exe'
    if (-not (Test-Path -LiteralPath $BuiltExe)) {
        throw "Nuitka产物中缺少TokenAnalyzer.exe：$($BuiltDirectory.FullName)"
    }

    $StandalonePending = Join-Path $DistRoot 'TokenAnalyzer.pending'
    Remove-BuildPath -Path $StandalonePending
    Copy-Item -LiteralPath $BuiltDirectory.FullName -Destination $StandalonePending -Recurse
    if (-not (Test-Path -LiteralPath (Join-Path $StandalonePending 'TokenAnalyzer.exe'))) {
        throw '复制独立应用目录失败。'
    }
    Remove-BuildPath -Path $StandaloneTarget
    Move-Item -LiteralPath $StandalonePending -Destination $StandaloneTarget

    Write-Host "独立应用已生成：$StandaloneTarget"
    if ($SkipInstaller) {
        return
    }

    Remove-BuildPath -Path $InstallerStage
    New-Item -ItemType Directory -Path $InstallerStage -Force | Out-Null
    $InnoArgs = @(
        "/DMyAppVersion=$Version",
        "/DSourceDir=$StandaloneTarget",
        "/DOutputDir=$InstallerStage",
        $InnoScript
    )
    & $InnoCompiler @InnoArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup构建失败，退出码：$LASTEXITCODE。上一次成功的安装包未被修改。"
    }

    $ExpectedInstallerName = "词元分析器-安装程序-$Version.exe"
    $StagedInstaller = Join-Path $InstallerStage $ExpectedInstallerName
    if (-not (Test-Path -LiteralPath $StagedInstaller)) {
        throw "Inno Setup未生成预期安装程序：$StagedInstaller"
    }

    New-Item -ItemType Directory -Path $InstallerTarget -Force | Out-Null
    $PendingInstaller = Join-Path $InstallerTarget ($ExpectedInstallerName + '.pending')
    Copy-Item -LiteralPath $StagedInstaller -Destination $PendingInstaller -Force
    if ((Get-Item -LiteralPath $PendingInstaller).Length -le 0) {
        throw '安装程序复制失败。'
    }

    $FinalInstaller = Join-Path $InstallerTarget $ExpectedInstallerName
    Move-Item -LiteralPath $PendingInstaller -Destination $FinalInstaller -Force
    Assert-PathInsideProject -Path $InstallerTarget
    Get-ChildItem -LiteralPath $InstallerTarget -File -Filter '*.exe' |
        Where-Object { $_.FullName -ne $FinalInstaller } |
        Remove-Item -Force
    Write-Host "安装程序已生成：$FinalInstaller"
} finally {
    if (Test-Path -LiteralPath $LockPath) {
        Remove-Item -LiteralPath $LockPath -Force
    }
}
