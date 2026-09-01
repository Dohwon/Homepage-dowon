param(
  [Parameter(Mandatory = $true)][string]$Distro,
  [Parameter(Mandatory = $true)][string]$WslUser,
  [Parameter(Mandatory = $true)][string]$ScriptPath,
  [ValidateSet("Install", "Check", "Remove")][string]$Mode = "Install"
)

$ErrorActionPreference = "Stop"
$taskName = "Dowon Project Atlas Sync"

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

$arguments = "-d `"$Distro`" --user `"$WslUser`" --exec bash `"$ScriptPath`""
$wslExecutable = Join-Path $env:WINDIR "System32\wsl.exe"
$action = New-ScheduledTaskAction -Execute $wslExecutable -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date).Date.AddHours(3)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Description "Detect and publish Project Atlas project-folder changes from WSL once a day." -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Output "Installed Windows task: $taskName"
