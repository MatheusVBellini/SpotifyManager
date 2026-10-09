param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Python executable does not exist.' }
$scriptPath = Join-Path $PSScriptRoot 'spotify_sync.py'
$configPath = Join-Path $PSScriptRoot 'config.json'
$logPath = Join-Path $PSScriptRoot 'sync.log'
$syncArguments = @($scriptPath, 'sync', '--config', $configPath, '--log-file', $logPath)
if ($Preview) { $syncArguments += '--dry-run' }
& $PythonPath @syncArguments
exit $LASTEXITCODE
