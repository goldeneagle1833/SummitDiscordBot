# PowerShell script to set up a Windows Scheduled Task for automatic log pulling
# Run as Administrator
# Usage: .\scripts\setup_scheduled_task.ps1

param(
    [ValidateSet('Daily', 'Weekly', 'Hourly')]
    [string]$Frequency = 'Daily',
    [int]$Hour = 2,  # Default: 2 AM
    [int]$Minute = 0
)

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Error: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Get the current directory (project root)
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
$pullLogsScript = Join-Path $scriptPath "pull_logs.ps1"

if (-not (Test-Path $pullLogsScript)) {
    Write-Host "Error: pull_logs.ps1 not found at $pullLogsScript" -ForegroundColor Red
    exit 1
}

# Task name
$taskName = "Summit Bot - Pull Logs"

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    $response = Read-Host "A scheduled task with name '$taskName' already exists. Replace it? (y/n)"
    if ($response -ne 'y') {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the action
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$pullLogsScript`"" `
    -WorkingDirectory $projectRoot

# Create the trigger based on frequency
switch ($Frequency) {
    'Hourly' {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours($Hour).AddMinutes($Minute) -RepetitionInterval (New-TimeSpan -Hours 1)
        $freqDesc = "every hour"
    }
    'Daily' {
        $trigger = New-ScheduledTaskTrigger -Daily -At "$($Hour):$($Minute.ToString('00'))"
        $freqDesc = "daily at $($Hour):$($Minute.ToString('00'))"
    }
    'Weekly' {
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "$($Hour):$($Minute.ToString('00'))"
        $freqDesc = "weekly on Monday at $($Hour):$($Minute.ToString('00'))"
    }
}

# Create the principal (run whether user is logged in or not)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U

# Create the settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Automatically pulls log files from Summit Discord Bot server"

    Write-Host "`n✓ Scheduled task created successfully!" -ForegroundColor Green
    Write-Host "Task Name: $taskName" -ForegroundColor Cyan
    Write-Host "Frequency: $freqDesc" -ForegroundColor Cyan
    Write-Host "Script: $pullLogsScript" -ForegroundColor Cyan
    Write-Host "`nThe task will run $freqDesc and save logs to the 'logs' directory." -ForegroundColor White
    Write-Host "`nTo manage the task:" -ForegroundColor Yellow
    Write-Host "  - Open Task Scheduler (taskschd.msc)"
    Write-Host "  - Find '$taskName' under Task Scheduler Library"
    Write-Host "  - Right-click to Run, Edit, or Delete"
    Write-Host "`nOr use PowerShell commands:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName '$taskName'"
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
    Write-Host "  Unregister-ScheduledTask -TaskName '$taskName'"

} catch {
    Write-Host "`n✗ Failed to create scheduled task:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
