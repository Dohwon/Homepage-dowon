param(
  [Parameter(Mandatory = $true)][string]$Distro,
  [Parameter(Mandatory = $true)][string]$WslUser,
  [Parameter(Mandatory = $true)][string]$ScriptPath,
  [ValidateSet("Install", "Check", "Remove")][string]$Mode = "Install"
)

$ErrorActionPreference = "Stop"
$taskName = "Dowon Project Atlas Sync"
$wrapperPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "run-project-atlas-task.ps1"

if (-not (Test-Path $wrapperPath)) {
  throw "Project Atlas Windows wrapper is missing: $wrapperPath"
}

if ($Mode -eq "Remove") {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed Windows task: $taskName"
  exit 0
}

if ($Mode -eq "Check") {
  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName $taskName
  [pscustomobject]@{
    TaskName = $task.TaskName
    State = $task.State
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
    NextRunTime = $info.NextRunTime
  } | Format-List
  exit 0
}

$powershellExecutable = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$wrapperPath`" -Distro `"$Distro`" -WslUser `"$WslUser`" -ScriptPath `"$ScriptPath`""
$action = New-ScheduledTaskAction -Execute $powershellExecutable -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date).Date.AddHours(3)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Description "Detect and publish Project Atlas project-folder changes from WSL once a day." -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Output "Installed Windows task: $taskName"
