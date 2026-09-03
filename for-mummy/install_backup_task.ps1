# Register the nightly backup as a Windows scheduled task (step 10.5).
#
# ASCII ONLY in this file: Windows PowerShell 5.1 reads .ps1 as ANSI unless the
# file has a BOM, so a UTF-8 em-dash turns into mojibake and breaks parsing.
#
#   powershell -ExecutionPolicy Bypass -File install_backup_task.ps1
#   powershell -ExecutionPolicy Bypass -File install_backup_task.ps1 -Remove
#
# WHY A SCHEDULED TASK AND NOT "REMEMBER TO CLICK BACKUP"
#   A backup that depends on somebody remembering is not a backup. This runs at
#   9pm daily whether anyone thinks about it or not, and -RunOnlyIfIdle is NOT
#   set precisely so a busy machine still gets backed up.
#
#   It runs as the CURRENT USER, at that user's normal privilege - no admin
#   rights needed, matching the per-user install.
#
# WHAT IT DOES NOT DO
#   It does not copy the backup OFF this machine. A backup sitting on the same
#   disk as the database dies with that disk. Getting a copy off the box is a
#   separate, manual decision (see docs/INSTALL_GUIDE.md) - deliberately not
#   automated here, because it needs a destination only the owner can choose.

param(
    [switch]$Remove,
    [string]$Time = "21:00"
)

$ErrorActionPreference = "Stop"
$TaskName = "Dental Clinic - nightly backup"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed the scheduled task."
    } else {
        Write-Host "No scheduled task to remove."
    }
    return
}

# The task must point at the INSTALLED backup.exe, not at this script's folder.
$installRoot = Join-Path $env:LOCALAPPDATA "Dental Clinic"
$backupExe = Join-Path $installRoot "backup.exe"

if (-not (Test-Path $backupExe)) {
    Write-Error "backup.exe not found at $backupExe. Install the Dental Clinic app first."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $backupExe -WorkingDirectory $installRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time

# StartWhenAvailable: if the PC was off at 9pm, back up when it next starts -
# a clinic PC is switched off overnight more often than not.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Backs up the clinic's database and X-ray files every night." `
    -Force | Out-Null

Write-Host "Scheduled a nightly backup at $Time."
Write-Host "  runs:    $backupExe"
Write-Host "  saves to: $env:LOCALAPPDATA\ClinicApp\backups"
Write-Host ""
Write-Host "IMPORTANT: this keeps backups on THIS computer only. If the disk"
Write-Host "fails you lose the backups too. Copy them to a pen drive or cloud"
Write-Host "folder regularly - see the install guide."
