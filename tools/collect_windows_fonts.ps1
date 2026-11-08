<#
.SYNOPSIS
    Stage the Windows-only fonts the templates use, so a Linux render box can
    produce pixel-identical output.

.DESCRIPTION
    The templates reference font="Consolas" in 49 places, plus "Segoe UI" and
    "Arial". Those ship with Windows, not with Linux. Without them Pango falls
    back to some default face and the cloud render silently drifts from the
    laptop render - different glyph widths, shifted layouts, different number
    columns.

    This copies them from C:\Windows\Fonts into a local staging folder that
    tools\runpod_render.ps1 -SyncAssets uploads to your own private pod.
    Nothing is published anywhere; these go from your machine to your box.

.EXAMPLE
    .\tools\collect_windows_fonts.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is not reliably bound inside param() defaults under -File, so
# resolve the repo-relative default here instead.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutDir) { $OutDir = Join-Path $scriptDir "..\.fonts_stage" }
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$src = Join-Path $env:WINDIR "Fonts"

# Families the templates actually ask for, with their regular/bold/italic faces.
$patterns = @(
    "consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf",   # Consolas
    "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuil.ttf",   # Segoe UI
    "arial.ttf",   "arialbd.ttf",  "ariali.ttf"                      # Arial
)

$copied  = @()
$missing = @()

foreach ($p in $patterns) {
    $file = Join-Path $src $p
    if (Test-Path $file) {
        Copy-Item $file -Destination $OutDir -Force
        $copied += $p
    } else {
        $missing += $p
    }
}

# The OFL fonts the repo bundles itself. assets/ is gitignored (.gitignore:46),
# so a git clone on the box arrives WITHOUT Anton and Space Grotesk - they have
# to travel with the fonts.
$repoFonts = Join-Path $PSScriptRoot "..\assets\fonts"
if (Test-Path $repoFonts) {
    Get-ChildItem $repoFonts -Filter *.ttf | ForEach-Object {
        Copy-Item $_.FullName -Destination $OutDir -Force
        $copied += $_.Name
    }
}

Write-Host ""
Write-Host "Staged $($copied.Count) font file(s) -> $OutDir" -ForegroundColor Green
$copied | Sort-Object | ForEach-Object { Write-Host "    $_" }

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Not found on this machine (usually fine - these are optional faces):" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "    $_" }
}

# The four families that MUST exist or the cloud render will not match.
$required = @{
    "Consolas"      = "consola.ttf"
    "Segoe UI"      = "segoeui.ttf"
    "Montserrat"    = "Montserrat-Regular.ttf"
    "Anton"         = "Anton-Regular.ttf"
    "Space Grotesk" = "SpaceGrotesk-Bold.ttf"
}
$hard = @()
foreach ($name in $required.Keys) {
    if (-not (Test-Path (Join-Path $OutDir $required[$name]))) { $hard += "$name ($($required[$name]))" }
}
if ($hard.Count -gt 0) {
    Write-Host ""
    Write-Host "MISSING REQUIRED FONTS - cloud output will not match local:" -ForegroundColor Red
    $hard | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    exit 1
}

Write-Host ""
Write-Host "All required families present. Next: .\tools\runpod_render.ps1 -SyncAssets ..." -ForegroundColor Green
