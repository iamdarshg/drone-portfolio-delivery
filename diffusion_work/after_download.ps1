# Wait on the existing downloader process handle, not a repeated status poll.
param([int]$DownloaderPid = 29432)
$ErrorActionPreference = 'Stop'
if (Get-Process -Id $DownloaderPid -ErrorAction SilentlyContinue) {
    Wait-Process -Id $DownloaderPid
}
$code = '<SOURCE_CHECKOUT>'
$python = 'E:/OneLine_diffusion/venv/Scripts/python.exe'
# Rehash/reconcile the whole approved bundle; downloader safely resumes if needed.
& $python -B "$code/download_wan.py"
if ($LASTEXITCODE -ne 0) { throw 'Download/hash verification failed; inference NOT launched' }
& $python -B "$code/wan_compact.py" --run wan_smoke_s42
if ($LASTEXITCODE -ne 0) { throw 'Wan baseline failed/deferred; inspect E: stage logs' }
