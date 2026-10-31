<# Install graph-ma and UA. Requires Python 3.10+; see README for UA prerequisites. #>
param(
    [switch]$SkipUA,
    [switch]$Replace,
    [string]$SkillsDir,
    [string]$UADir,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$installerArgs = @((Join-Path $PSScriptRoot 'scripts/install.py'))
if ($SkipUA) { $installerArgs += '--skip-ua' }
if ($Replace) { $installerArgs += '--replace' }
if ($SkillsDir) { $installerArgs += @('--skills-dir', $SkillsDir) }
if ($UADir) { $installerArgs += @('--ua-dir', $UADir) }
if ($Help) { $installerArgs += '--help' }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @installerArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @installerArgs
} else {
    throw 'Python 3.10+ is required. Install Python and run this script again.'
}
if ($LASTEXITCODE -ne 0) { throw "graph-ma installation failed (exit $LASTEXITCODE)." }
