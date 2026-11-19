#Requires -Version 5.1
<#
.SYNOPSIS
    Cree ou supprime les raccourcis du menu Demarrage des trois applications Lattice.
.DESCRIPTION
    Un seul raccourci par application, dans <Programs>\Lattice. AUCUN raccourci n'est
    cree sur le Bureau : convention utilisateur non negociable (les lanceurs vont dans
    le menu des applications, jamais sur le Bureau). Chaque raccourci cible le binaire
    PyInstaller construit par build_exe.ps1 lorsqu'il existe, sinon pythonw.exe avec le
    point d'entree GUI. Le script est idempotent et affiche une ligne nommee en cas
    d'echec. Le raccourci PhotoCraft facultatif est seulement signale, jamais cree.
.PARAMETER App
    dither, glyph, glitch ou all (defaut all).
.PARAMETER Uninstall
    Supprime les raccourcis au lieu de les creer.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('dither', 'glyph', 'glitch', 'all')][string]$App = 'all',
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$EntryDir = Join-Path $PSScriptRoot 'packaging\entry'
$DistDir = Join-Path $ProjectRoot 'dist'
$ProgramsDir = [Environment]::GetFolderPath('Programs')
$InstallDir = Join-Path $ProgramsDir 'Lattice'
$Apps = if ($App -eq 'all') { @('dither', 'glyph', 'glitch') } else { @($App) }

function Fail([string]$Label, [string]$Message) {
    throw "LATTICE INSTALL ERROR: ${Label}: ${Message}"
}

function Get-AppInfo([string]$AppName) {
    $entry = Join-Path $EntryDir "${AppName}_gui.py"
    $info = @{
        dither = @{
            Title = 'Lattice Dither'; Exe = 'LatticeDither.exe'; Entry = $entry
            Icon = (Join-Path $ProjectRoot 'assets\lattice_dither.ico')
            Description = 'Lattice Dither - dithering studio for PhotoCraft'
        }
        glyph = @{
            Title = 'Lattice Glyph'; Exe = 'LatticeGlyph.exe'; Entry = $entry
            Icon = $null
            Description = 'Lattice Glyph - glyph, bitmask and text rendering'
        }
        glitch = @{
            Title = 'Lattice Glitch'; Exe = 'LatticeGlitch.exe'; Entry = $entry
            Icon = $null
            Description = 'Lattice Glitch - feedback, displacement and signal degradation'
        }
    }
    if (-not $info.ContainsKey($AppName)) { Fail $AppName 'application inconnue' }
    return $info[$AppName]
}

function Get-Target([hashtable]$Info, [string]$AppName) {
    $exe = Join-Path $DistDir $Info.Exe
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        return @{ Target = $exe; Arguments = '' }
    }
    if (-not (Test-Path -LiteralPath $Pythonw -PathType Leaf)) {
        Fail $AppName "ni binaire ($exe) ni pythonw.exe ($Pythonw)"
    }
    if (-not (Test-Path -LiteralPath $Info.Entry -PathType Leaf)) {
        Fail $AppName "point d'entree GUI absent: $($Info.Entry)"
    }
    return @{ Target = $Pythonw; Arguments = ('"{0}"' -f $Info.Entry) }
}

function Get-Shortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    return $shell.CreateShortcut($Path)
}

function Test-ShortcutCurrent([string]$Path, [string]$Target, [string]$Arguments) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $link = Get-Shortcut $Path
    return (($link.TargetPath -eq $Target) -and
            ($link.Arguments -eq $Arguments) -and
            ($link.WorkingDirectory -eq $ProjectRoot))
}

function New-AppShortcut([string]$Path, [hashtable]$Info, [hashtable]$Launch) {
    $link = Get-Shortcut $Path
    $link.TargetPath = $Launch.Target
    $link.Arguments = $Launch.Arguments
    $link.WorkingDirectory = $ProjectRoot
    $link.Description = $Info.Description
    $link.WindowStyle = 1
    if ($Info.Icon -and (Test-Path -LiteralPath $Info.Icon -PathType Leaf)) {
        $link.IconLocation = "$($Info.Icon),0"
    }
    $link.Save()
}

if ([string]::IsNullOrEmpty($ProgramsDir)) {
    Fail 'menu' 'dossier du menu Demarrage introuvable'
}

Write-Host 'Lattice - raccourcis du menu Demarrage (aucun sur le Bureau)'
Write-Host "  racine projet : $ProjectRoot"
Write-Host "  dossier menu  : $InstallDir"

foreach ($application in $Apps) {
    $info = Get-AppInfo $application
    $path = Join-Path $InstallDir "$($info.Title).lnk"
    if ($Uninstall) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Write-Host "$($info.Title): rien a supprimer ($path)"
            continue
        }
        if ($PSCmdlet.ShouldProcess($path, 'Supprimer le raccourci')) {
            Remove-Item -LiteralPath $path -Force
            Write-Host "$($info.Title): supprime $path"
        }
        continue
    }

    $launch = Get-Target $info $application
    if (Test-ShortcutCurrent $path $launch.Target $launch.Arguments) {
        Write-Host "$($info.Title): a jour ($path)"
        continue
    }
    if ($WhatIfPreference) {
        Write-Host "$($info.Title): creerait $path -> $($launch.Target) $($launch.Arguments)"
    }
    if ($PSCmdlet.ShouldProcess($path, "Creer le raccourci vers $($launch.Target)")) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        New-AppShortcut $path $info $launch
        Write-Host "$($info.Title): cree $path"
    }
}

if (-not $Uninstall -and $Apps -contains 'dither') {
    $photoCraft = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PhotoCraft (Lattice Dither).lnk'
    if (Test-Path -LiteralPath $photoCraft -PathType Leaf) {
        Write-Host "  PhotoCraft: present ($photoCraft) - non modifie"
    } else {
        Write-Warning "PhotoCraft absent ($photoCraft) - Lattice ne le cree pas"
    }
}

Write-Host 'LATTICE INSTALL OK'
exit 0
