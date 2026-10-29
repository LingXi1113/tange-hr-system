$ErrorActionPreference = 'Stop'
$sourcePath = [IO.Path]::GetFullPath($PSScriptRoot)
$desktopPath = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Desktop'))
$targetPath = [IO.Path]::GetFullPath((Join-Path $desktopPath 'tange-hr-moka-improvements'))
if (-not $targetPath.StartsWith($desktopPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must be inside Desktop.'
}
if (Test-Path -LiteralPath $targetPath) { throw 'Destination already exists. Rename that folder before retrying.' }
& robocopy $sourcePath $targetPath /E /XD node_modules .venv dist __pycache__ /R:1 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) { throw "Copy failed: $LASTEXITCODE" }
Write-Host "Project copied to: $targetPath"
exit 0
