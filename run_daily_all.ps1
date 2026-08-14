$ErrorActionPreference = "Continue"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\Users\orang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Topics = @("ai", "commercial_space", "display_polarizer")
$LogDir = Join-Path $ProjectDir "logs"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "daily_all_$Stamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $ProjectDir

function Write-Log {
    param([string]$Message)
    $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

function Run-Step {
    param(
        [string]$Name,
        [string[]]$ArgsList
    )
    Write-Log "START $Name"
    & $Python @ArgsList 2>&1 | Tee-Object -FilePath $LogFile -Append
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0) {
        Write-Log "DONE  $Name"
    } else {
        Write-Log "FAIL  $Name exit=$ExitCode"
    }
}

Write-Log "=== Unified news daily job started ==="

foreach ($Topic in $Topics) {
    Run-Step "report:$Topic" @("run_llm.py", "--topic", $Topic, "--refresh")
}

foreach ($Topic in $Topics) {
    Run-Step "health:$Topic" @("run.py", "--topic", $Topic, "--health-check")
}

Write-Log "=== Unified news daily job finished ==="
