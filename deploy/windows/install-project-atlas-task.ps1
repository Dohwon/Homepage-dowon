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
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Description "Validate and publish Project Atlas changes from WSL every 15 minutes." -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Output "Installed Windows task: $taskName"
