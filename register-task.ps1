param(
    [string]$PythonPath = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    [string]$TaskName = 'SpotifyManager Playlist Sync',
    [ValidateRange(5, 1440)][int]$EveryMinutes = 15
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Project Python not found. Run python setup_env.py first, or provide -PythonPath.' }
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
if (-not (Test-Path -LiteralPath $resolvedPython -PathType Leaf)) { throw 'Python executable does not exist.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'config.json'))) { throw 'Create config.json and authorize first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'credentials.json'))) { throw 'Create credentials.json and authorize first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.spotify-sync\token.json'))) { throw 'Run auth before installing the task.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw "Task '$TaskName' already exists; choose a different TaskName or remove the existing task first." }
$taskPython = $resolvedPython
$windowlessPython = Join-Path (Split-Path -Parent $resolvedPython) 'pythonw.exe'
if ((Split-Path -Leaf $resolvedPython) -eq 'python.exe' -and (Test-Path -LiteralPath $windowlessPython -PathType Leaf)) { $taskPython = $windowlessPython }
$scriptPath = Join-Path $PSScriptRoot 'spotify_sync.py'
$configPath = Join-Path $PSScriptRoot 'config.json'
$logPath = Join-Path $PSScriptRoot 'sync.log'
$arguments = '"' + $scriptPath + '" sync --config "' + $configPath + '" --log-file "' + $logPath + '"'
$action = New-ScheduledTaskAction -Execute $taskPython -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Append missing child playlist items to configured Spotify parents.'
Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
Write-Host "Created '$TaskName', every $EveryMinutes minutes while you are logged in. Logs: $(Join-Path $PSScriptRoot 'sync.log')"
