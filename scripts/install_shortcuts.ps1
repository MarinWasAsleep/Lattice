#Requires -Version 5.1
<#
.SYNOPSIS
    Create or remove the DitherCraft Desktop and Start Menu shortcuts.
.DESCRIPTION
    Creates exactly two shortcuts, both starting DitherCraft with the project virtual
    environment: <Desktop>\DitherCraft.lnk and <Start Menu>\Programs\DitherCraft.lnk.
    The script is idempotent: a shortcut that already points at the right interpreter and
    launcher is left untouched. It never creates a PhotoCraft shortcut; the existing
    "PhotoCraft (DitherCraft)" Desktop shortcut is only checked and reported.
.PARAMETER Uninstall
    Remove the two DitherCraft shortcuts instead of creating them.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1 -WhatIf
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonwPath = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$LauncherPath = Join-Path $ProjectRoot 'DitherCraft.pyw'
$IconPath = Join-Path $ProjectRoot 'assets\dithercraft.ico'
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$ProgramsDir = [Environment]::GetFolderPath('Programs')
$PhotoCraftShortcut = Join-Path $DesktopDir 'PhotoCraft (DitherCraft).lnk'
$ShortcutArguments = '"{0}"' -f $LauncherPath
$Shortcuts = @(
    [pscustomobject]@{ Name = 'Desktop'; Path = (Join-Path $DesktopDir 'DitherCraft.lnk') }
    [pscustomobject]@{ Name = 'Start Menu'; Path = (Join-Path $ProgramsDir 'DitherCraft.lnk') }
)

function Get-Shortcut {
    <#
    .SYNOPSIS
        Return the WScript.Shell shortcut object for Path; nothing is written until Save().
    #>
    param([Parameter(Mandatory)][string]$Path)
    $shell = New-Object -ComObject WScript.Shell
    return $shell.CreateShortcut($Path)
}

function Test-Prerequisites {
    <#
    .SYNOPSIS
        Return $true when the interpreter, the launcher and the icon are usable.
    #>
    $ok = $true
    foreach ($item in @(
        @{ Path = $PythonwPath; Label = 'pythonw.exe' },
        @{ Path = $LauncherPath; Label = 'DitherCraft.pyw' },
        @{ Path = $IconPath; Label = 'dithercraft.ico' }
    )) {
        if (Test-Path -LiteralPath $item.Path -PathType Leaf) { continue }
        $ok = $false
        $message = "$($item.Label) not found: $($item.Path)"
        if ($WhatIfPreference) { Write-Warning $message } else { throw $message }
    }
    if ($ok) {
        $launcherText = Get-Content -LiteralPath $LauncherPath -Raw -Encoding utf8
        if ([string]::IsNullOrWhiteSpace($launcherText)) {
            $ok = $false
            $message = "launcher is empty: $LauncherPath"
            if ($WhatIfPreference) { Write-Warning $message } else { throw $message }
        }
    }
    return $ok
}

function Test-ShortcutCurrent {
    <#
    .SYNOPSIS
        Return $true when Path is a shortcut that already starts DitherCraft correctly.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Arguments
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $link = Get-Shortcut -Path $Path
    $sameTarget = $link.TargetPath -eq $Target
    $sameArguments = $link.Arguments -eq $Arguments
    $sameDirectory = $link.WorkingDirectory -eq $ProjectRoot
    return $sameTarget -and $sameArguments -and $sameDirectory
}

function New-DitherCraftShortcut {
    <#
    .SYNOPSIS
        Write the shortcut at Path so that it starts DitherCraft with pythonw.exe.
    #>
    param([Parameter(Mandatory)][string]$Path)
    $link = Get-Shortcut -Path $Path
    $link.TargetPath = $PythonwPath
    $link.Arguments = $ShortcutArguments
    $link.WorkingDirectory = $ProjectRoot
    $link.IconLocation = "$IconPath,0"
    $link.Description = 'DitherCraft - dithering tool for PhotoCraft'
    $link.WindowStyle = 1
    $link.Save()
}

if ([string]::IsNullOrEmpty($DesktopDir) -or [string]::IsNullOrEmpty($ProgramsDir)) {
    throw 'Could not resolve the Desktop or the Start Menu folder.'
}

Write-Host 'DitherCraft shortcuts'
Write-Host "  project root : $ProjectRoot"
Write-Host "  interpreter  : $PythonwPath"
Write-Host "  launcher     : $LauncherPath"

$ready = Test-Prerequisites

if (Test-Path -LiteralPath $PhotoCraftShortcut -PathType Leaf) {
    Write-Host "  PhotoCraft   : present ($PhotoCraftShortcut)"
} else {
    Write-Warning "PhotoCraft shortcut missing: $PhotoCraftShortcut (DitherCraft does not create it)"
}

foreach ($shortcut in $Shortcuts) {
    if ($Uninstall) {
        if (-not (Test-Path -LiteralPath $shortcut.Path -PathType Leaf)) {
            Write-Host "$($shortcut.Name): nothing to remove ($($shortcut.Path))"
            continue
        }
        if ($PSCmdlet.ShouldProcess($shortcut.Path, 'Remove shortcut')) {
            Remove-Item -LiteralPath $shortcut.Path -Force
            Write-Host "$($shortcut.Name): removed $($shortcut.Path)"
        }
        continue
    }
    if (-not $ready) { continue }
    if (Test-ShortcutCurrent -Path $shortcut.Path -Target $PythonwPath -Arguments $ShortcutArguments) {
        Write-Host "$($shortcut.Name): up to date ($($shortcut.Path))"
        continue
    }
    if ($WhatIfPreference) {
        Write-Host "$($shortcut.Name): would create $($shortcut.Path) -> $PythonwPath $ShortcutArguments"
    }
    if ($PSCmdlet.ShouldProcess($shortcut.Path, "Create shortcut to $PythonwPath $ShortcutArguments")) {
        New-DitherCraftShortcut -Path $shortcut.Path
        Write-Host "$($shortcut.Name): created $($shortcut.Path)"
    }
}

if (-not $ready) {
    Write-Warning 'Shortcuts were not created because a required file is missing.'
    exit 1
}

exit 0
