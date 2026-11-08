<#
.SYNOPSIS
    Render jobs on a RunPod CPU pod (or any SSH box) and pull the videos back.

.DESCRIPTION
    Manim's Cairo renderer is single-threaded and CPU-bound, so throughput comes
    from running many renders at once - not from a GPU. This drives a many-core
    Linux box: it packs the code + selected job folders, uploads them, runs
    render_batch.py with N parallel workers, and downloads the finished mp4s.

    Phase 4 needs no API keys, so .env never leaves this machine.

    The pod itself is created/terminated in the RunPod console (or with
    runpodctl). Pass its SSH host/port here.

.EXAMPLE
    # one-time, after creating the pod + network volume:
    .\tools\collect_windows_fonts.ps1
    .\tools\runpod_render.ps1 -PodHost 1.2.3.4 -PodPort 40022 -Bootstrap -SyncAssets -Jobs jobs\auto\auto_12

.EXAMPLE
    # every day after that:
    .\tools\runpod_render.ps1 -PodHost 1.2.3.4 -PodPort 40022 -All

.NOTES
    Downloaded output/ folders OVERWRITE the local ones. Keep any baseline you
    care about under a different name before running.
#>
[CmdletBinding()]
param(
    [string[]]$Jobs,
    [switch]$All,

    [string]$PodHost = $env:RUNPOD_HOST,
    [int]$PodPort    = 22,
    [string]$PodUser = "root",
    [string]$SshKey  = (Join-Path $env:USERPROFILE ".ssh\id_ed25519"),

    [int]$Workers    = 0,
    [string]$Quality = "h",

    [switch]$Bootstrap,
    [switch]$SyncAssets,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$KeepBundle,

    [string]$RemoteRoot  = "/workspace/repo",
    [string]$RemotePy    = "/workspace/venv/bin/python",
    [string]$RemoteInbox = "/workspace/inbox",

    # Optional: if runpodctl is installed and you pass the pod id, the pod is
    # terminated when the run finishes (including on failure).
    [string]$PodId,
    [switch]$TerminateWhenDone
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host ""; Write-Host "=== $msg ===" -ForegroundColor Cyan }

# ---------------------------------------------------------------- preflight --
foreach ($c in @("ssh", "scp", "tar")) {
    if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Fail "$c not found on PATH." }
}
# -DryRun only previews what would be sent, so it does not need a live pod.
if (-not $DryRun) {
    if (-not $PodHost) {
        Fail "No -PodHost. Pass it, or set `$env:RUNPOD_HOST. Get it from the RunPod console (Connect -> SSH)."
    }
    if (-not (Test-Path $SshKey)) {
        Fail "SSH key not found: $SshKey`nGenerate one with: ssh-keygen -t ed25519`nThen add the .pub to RunPod -> Settings -> SSH Public Keys."
    }
}

$sshTarget = "$PodUser@$PodHost"
$sshArgs   = @("-i", $SshKey, "-p", "$PodPort", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15")
$scpArgs   = @("-i", $SshKey, "-P", "$PodPort", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15")

function Invoke-Ssh([string]$RemoteCmd, [switch]$AllowFail) {
    & ssh @sshArgs $sshTarget $RemoteCmd
    if ($LASTEXITCODE -ne 0 -and -not $AllowFail) { Fail "remote command failed (exit $LASTEXITCODE): $RemoteCmd" }
    return $LASTEXITCODE
}
function Send-File([string]$Local, [string]$Remote) {
    & scp @scpArgs $Local "${sshTarget}:$Remote"
    if ($LASTEXITCODE -ne 0) { Fail "upload failed: $Local -> $Remote" }
}
function Receive-File([string]$Remote, [string]$Local) {
    & scp @scpArgs "${sshTarget}:$Remote" $Local
    if ($LASTEXITCODE -ne 0) { Fail "download failed: $Remote -> $Local" }
}

# ------------------------------------------------------------ job selection --
$jobsRoot = Join-Path $repoRoot "jobs"
$selected = New-Object System.Collections.Generic.List[string]

if ($All) {
    Get-ChildItem $jobsRoot -Recurse -Filter "job.json" -File | ForEach-Object {
        $dir = $_.Directory.FullName
        $done = Test-Path (Join-Path $dir "output\final.mp4")
        if ($Force -or -not $done) {
            $selected.Add(($dir.Substring($repoRoot.Length).TrimStart('\','/') -replace '\\','/'))
        }
    }
} elseif ($Jobs) {
    foreach ($j in $Jobs) {
        $p = $j
        if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $repoRoot $j }
        $p = [System.IO.Path]::GetFullPath($p)
        if (-not (Test-Path (Join-Path $p "job.json"))) { Fail "no job.json in $p" }
        $selected.Add(($p.Substring($repoRoot.Length).TrimStart('\','/') -replace '\\','/'))
    }
} elseif (-not ($Bootstrap -or $SyncAssets)) {
    Fail "Pass -Jobs <dir>... or -All (or -Bootstrap / -SyncAssets for setup only)."
}

# Phase 4 reads job.json + audio/ + script/script.json. Catch a broken job here,
# not 40 minutes into a billed pod.
foreach ($rel in $selected) {
    $abs = Join-Path $repoRoot $rel
    if (-not (Test-Path (Join-Path $abs "script\script.json"))) { Fail "$rel is missing script/script.json" }
    $audio = Join-Path $abs "audio"
    if (-not (Test-Path $audio)) { Fail "$rel is missing audio/" }
    if ((Get-ChildItem $audio -File -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
        Fail "$rel has an empty audio/ folder"
    }
}

Write-Host ""
Write-Host "Pod   : $sshTarget (port $PodPort)"
Write-Host "Repo  : $repoRoot"
Write-Host "Jobs  : $($selected.Count)"
foreach ($rel in $selected) { Write-Host "        $rel" }
if ($DryRun) { Write-Host ""; Write-Host "[dry-run] nothing sent." -ForegroundColor Yellow; exit 0 }

$stamp     = Get-Date -Format "yyyyMMdd_HHmmss"
$tmp       = Join-Path $env:TEMP "autoshorts_$stamp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$startedAt = Get-Date

try {
    Invoke-Ssh "mkdir -p '$RemoteRoot' '$RemoteInbox' /workspace/fonts"

    # ------------------------------------------------------------- assets ----
    if ($SyncAssets) {
        Step "uploading assets + fonts"
        $fontStage = Join-Path $repoRoot ".fonts_stage"
        if (-not (Test-Path $fontStage)) {
            Fail "No .fonts_stage folder. Run .\tools\collect_windows_fonts.ps1 first."
        }
        # assets/ is gitignored (.gitignore:46) - Anton and SpaceGrotesk are not
        # in git at all, so a clone on the pod would be missing them. They can
        # only get there this way.
        $assetsTgz = Join-Path $tmp "assets.tgz"
        & tar -czf $assetsTgz -C $repoRoot --exclude="*.pyc" "assets"
        if ($LASTEXITCODE -ne 0) { Fail "could not pack assets/" }
        Send-File $assetsTgz "$RemoteInbox/assets.tgz"
        Invoke-Ssh "tar -xzf '$RemoteInbox/assets.tgz' -C '$RemoteRoot'"

        $fontsTgz = Join-Path $tmp "fonts.tgz"
        & tar -czf $fontsTgz -C $fontStage "."
        if ($LASTEXITCODE -ne 0) { Fail "could not pack .fonts_stage/" }
        Send-File $fontsTgz "$RemoteInbox/fonts.tgz"
        Invoke-Ssh "tar -xzf '$RemoteInbox/fonts.tgz' -C /workspace/fonts && mkdir -p /root/.fonts && cp -f /workspace/fonts/*.ttf /root/.fonts/ && fc-cache -f > /dev/null && echo 'fonts installed:' && fc-list | grep -icE 'consolas|segoe|montserrat|anton|grotesk'"
    }

    # ------------------------------------------------------- code + jobs -----
    Step "packing code + jobs"
    $bundle = Join-Path $tmp "bundle.tgz"
    $paths  = @("main.py", "captions.py", "render_batch.py", "templates.json", "manim.cfg",
                "requirements.txt", "requirements-render.txt", "src")
    foreach ($rel in $selected) { $paths += $rel }

    # media/ and output/ are regenerated on the pod - shipping them would waste
    # most of the upload.
    $tarArgs = @("-czf", $bundle, "-C", $repoRoot,
                 "--exclude=*/media", "--exclude=*/media/*",
                 "--exclude=*/output", "--exclude=*/output/*",
                 "--exclude=__pycache__", "--exclude=*.pyc",
                 "--exclude=*/logs/*", "--exclude=.venv") + $paths
    & tar @tarArgs
    if ($LASTEXITCODE -ne 0) { Fail "could not build the upload bundle" }
    $mb = [math]::Round((Get-Item $bundle).Length / 1MB, 1)
    Write-Host "bundle: $mb MB"

    Step "uploading"
    Send-File $bundle "$RemoteInbox/bundle.tgz"
    Invoke-Ssh "tar -xzf '$RemoteInbox/bundle.tgz' -C '$RemoteRoot'"

    # ---------------------------------------------------------- bootstrap ----
    if ($Bootstrap) {
        Step "bootstrapping the volume (one-time)"
        Send-File (Join-Path $PSScriptRoot "runpod_bootstrap.sh") "$RemoteInbox/bootstrap.sh"
        Invoke-Ssh "bash '$RemoteInbox/bootstrap.sh'"
    }

    if ($selected.Count -eq 0) {
        Write-Host ""
        Write-Host "Setup done, no jobs requested." -ForegroundColor Green
        exit 0
    }

    # ------------------------------------------------------------- render ----
    Step "rendering on pod"
    $cores = (& ssh @sshArgs $sshTarget "nproc").Trim()
    Write-Host "pod cores: $cores"

    $workerArg = ""
    if ($Workers -gt 0) { $workerArg = "--workers $Workers" }

    $jobArgs = ($selected -join " ")
    $remoteCmd = "cd '$RemoteRoot' && $RemotePy render_batch.py --jobs $jobArgs $workerArg -q $Quality --force"
    Write-Host "> $remoteCmd"
    Write-Host ""
    $renderExit = Invoke-Ssh $remoteCmd -AllowFail

    # -------------------------------------------------------- download -------
    Step "downloading results"
    $outPaths = ($selected | ForEach-Object { "$_/output" }) -join " "
    # Only pack the ones that actually exist, so a partial batch still returns
    # whatever succeeded.
    # output/renders/ is main.py's local archive of previous finals (main.py:1074).
    # The pod's copy is redundant with final.mp4, so leave it behind.
    $packCmd = "cd '$RemoteRoot' && ls -d $outPaths 2>/dev/null | tar --exclude='*/renders' --exclude='*/renders/*' -czf /workspace/results.tgz -C '$RemoteRoot' -T - && echo packed"
    $packExit = Invoke-Ssh $packCmd -AllowFail

    if ($packExit -eq 0) {
        $results = Join-Path $tmp "results.tgz"
        Receive-File "/workspace/results.tgz" $results
        & tar -xzf $results -C $repoRoot
        if ($LASTEXITCODE -ne 0) { Fail "could not unpack results" }

        Write-Host ""
        foreach ($rel in $selected) {
            $mp4 = Join-Path $repoRoot "$rel\output\final.mp4"
            if (Test-Path $mp4) {
                $sz = [math]::Round((Get-Item $mp4).Length / 1MB, 1)
                Write-Host ("  OK   {0}  ({1} MB)" -f $rel, $sz) -ForegroundColor Green
            } else {
                Write-Host ("  MISS {0}  - no final.mp4 (see pod log: {1}/{0}/logs/render_batch.log)" -f $rel, $RemoteRoot) -ForegroundColor Red
            }
        }
    } else {
        Write-Host "No output folders on the pod - every render failed." -ForegroundColor Red
    }

    $wall = (Get-Date) - $startedAt
    Write-Host ""
    Write-Host ("Wall clock: {0:mm\:ss}  (pod billed for roughly this long)" -f $wall) -ForegroundColor Cyan
    if ($renderExit -ne 0) {
        Write-Host "render_batch.py reported failures - check the per-job logs above." -ForegroundColor Yellow
    }
}
finally {
    if (-not $KeepBundle -and (Test-Path $tmp)) {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    # An hourly pod left running is the one way this setup gets expensive.
    if ($TerminateWhenDone -and $PodId) {
        if (Get-Command runpodctl -ErrorAction SilentlyContinue) {
            Write-Host ""
            Write-Host "terminating pod $PodId ..." -ForegroundColor Yellow
            & runpodctl remove pod $PodId
        } else {
            Write-Host ""
            Write-Host "runpodctl not installed - TERMINATE POD $PodId IN THE CONSOLE." -ForegroundColor Red
        }
    } else {
        Write-Host ""
        Write-Host "REMINDER: the pod is still running and still billing. Stop it in the RunPod console when you're done." -ForegroundColor Yellow
    }
}
