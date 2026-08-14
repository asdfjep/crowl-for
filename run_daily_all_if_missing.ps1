$ErrorActionPreference = "Continue"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ProjectDir "run_daily_all.ps1"
$LogDir = Join-Path $ProjectDir "logs"
$Today = Get-Date -Format "yyyyMMdd"
$GateTime = Get-Date -Hour 9 -Minute 30 -Second 0
$Now = Get-Date

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-CatchupLog {
    param([string]$Message)
    $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $Line
    Add-Content -Path (Join-Path $LogDir "daily_all_catchup_$Today.log") -Value $Line -Encoding UTF8
}

if ($Now.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
    Write-CatchupLog "SKIP weekend; workday-only schedule."
    exit 0
}

if ($Now -lt $GateTime) {
    Write-CatchupLog "SKIP before 09:30; daily task will run later."
    exit 0
}

$SuccessLog = Get-ChildItem -Path $LogDir -Filter "daily_all_$Today*.log" -ErrorAction SilentlyContinue |
    Where-Object {
        $Content = Get-Content -Path $_.FullName -Raw -ErrorAction SilentlyContinue
        $Content -match "=== Unified news daily job finished ===" -and $Content -notmatch "\bFAIL\b"
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($SuccessLog) {
    Write-CatchupLog "SKIP already completed today: $($SuccessLog.FullName)"
    exit 0
}

Write-CatchupLog "RUN no successful daily log found for $Today; starting main daily job."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $MainScript
$ExitCode = $LASTEXITCODE
Write-CatchupLog "DONE main daily job exit=$ExitCode"
exit $ExitCode
