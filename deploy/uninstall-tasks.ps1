<#
  Removes the Pit Box scheduled tasks. Leaves your database, files and backups
  completely alone -- this only unregisters the schedule.

      .\deploy\uninstall-tasks.ps1
#>
$ErrorActionPreference = "Stop"

foreach ($name in @("Pit Box Server", "Pit Box Backup")) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "not installed: $name" -ForegroundColor DarkGray
        continue
    }
    try {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "removed: $name" -ForegroundColor Green
    } catch {
        Write-Host "could not remove '$name' - try an elevated PowerShell." -ForegroundColor Yellow
        Write-Host "  $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Your data is untouched: pitbox.db, storage\ and backups\ all remain." -ForegroundColor DarkGray
