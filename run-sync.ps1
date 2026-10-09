param(
    [string]$PythonPath = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Project Python not found. Run python setup_env.py first, or provide -PythonPath.' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$scriptPath = Join-Path $PSScriptRoot 'spotify_sync.py'
$configPath = Join-Path $PSScriptRoot 'config.json'
$logPath = Join-Path $PSScriptRoot 'sync.log'
$syncArguments = @($scriptPath, 'sync', '--config', $configPath, '--log-file', $logPath)
if ($Preview) { $syncArguments += '--dry-run' }
& $PythonPath @syncArguments
exit $LASTEXITCODE
