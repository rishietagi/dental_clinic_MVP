# Remove the old nightly backup scheduled task (superseded).
#
# ASCII ONLY in this file: Windows PowerShell 5.1 reads .ps1 as ANSI unless the
# file has a BOM, so a UTF-8 em-dash turns into mojibake and breaks parsing.
#
#   powershell -ExecutionPolicy Bypass -File install_backup_task.ps1
#
# THIS SCRIPT NO LONGER INSTALLS ANYTHING. It only cleans up the 9pm task that
# earlier builds registered.
#
# WHY THE 9PM TASK WAS WRONG
#   The clinic closes at 4-5pm and the PC is switched off, so the task almost
#   never ran at 9pm. -StartWhenAvailable then deferred it to the next morning's
#   boot, competing with everything else starting up.
#
#   Worse, and the real defect: a backup needs the DATABASE RUNNING. At 9pm on a
#   closed clinic, Postgres is not running - so even when the task did fire on a
#   machine left on, the backup could fail.
#
# WHAT REPLACES IT
#   The app now backs itself up when it is OPENED, at most once a day, in the
#   background (see start_daily_backup in packaging/launcher.py). That is the one
#   moment we know the database is up and the machine is in use, and it captures
#   yesterday's completed work before today's edits begin. Nothing to schedule,
#   nothing to remember, and nothing to re-register when moving to a new PC.

$ErrorActionPreference = "Stop"
$TaskName = "Dental Clinic - nightly backup"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed the old 9pm scheduled task."
    Write-Host "The app now backs up by itself when it is opened each day."
} else {
    Write-Host "No old scheduled task found - nothing to do."
    Write-Host "The app backs up by itself when it is opened each day."
}

Write-Host ""
Write-Host "REMINDER: backups are still kept on THIS computer only."
Write-Host "Copy the newest file from %LOCALAPPDATA%\ClinicApp\backups to a pen"
Write-Host "drive or cloud folder every week - see the install guide."
