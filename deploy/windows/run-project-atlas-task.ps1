param(
  [Parameter(Mandatory = $true)][string]$Distro,
  [Parameter(Mandatory = $true)][string]$WslUser,
  [Parameter(Mandatory = $true)][string]$ScriptPath
)

$ErrorActionPreference = "Continue"
$wslExecutable = Join-Path $env:WINDIR "System32\\wsl.exe"
$logDirectory = Join-Path $env:LOCALAPPDATA "ProjectAtlas"
$logPath = Join-Path $logDirectory "task-wrapper.log"
$attempts = 3

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

for ($attempt = 1; $attempt -le $attempts; $attempt++) {
  $startedAt = Get-Date -Format "o"
  $output = (& $wslExecutable -d $Distro --user $WslUser --exec bash $ScriptPath 2>&1 | Out-String).Trim()
  $exitCode = $LASTEXITCODE
  Add-Content -Path $logPath -Value "[$startedAt] attempt=$attempt exit=$exitCode`n$output"

  if ($exitCode -eq 0) {
    exit 0
  }

  if ($attempt -lt $attempts) {
    Start-Sleep -Seconds 60
  }
}

exit $exitCode
