# Waits for the current inventory run to exit, then re-runs only the failed / timed-out probes on LARGE.
param([int]$WaitPid = 8016)

$dir = $PSScriptRoot
$py = 'C:\Users\fintan.creedon\code\exploration\.venv\Scripts\python.exe'
$jupyter = 'C:\Users\fintan.creedon\code\exploration\.venv\Scripts\jupyter.exe'
$log = Join-Path $dir 'results\queue.log'

function Log($m) { "$(Get-Date -Format s) $m" | Out-File -FilePath $log -Append -Encoding utf8 }

Log "waiting for PID $WaitPid"
Wait-Process -Id $WaitPid -ErrorAction SilentlyContinue
Log "PID $WaitPid exited; patching notebook"
& $py (Join-Path $dir 'patch_env_overrides.py') *>> $log

$env:CARD_INV_WAREHOUSE = 'LARGE'
$env:CARD_INV_DEC_TIMEOUT_S = '3600'
$env:CARD_INV_RETRY_FAILED = '1'
Log "starting retry run on LARGE (timeout 3600s, retry failed)"
& $jupyter nbconvert --to notebook --execute card_datasets_inventory.ipynb --inplace `
    --ExecutePreprocessor.timeout=-1 --ExecutePreprocessor.kernel_name=exploration `
    1>> (Join-Path $dir 'results\run2.log') 2>> (Join-Path $dir 'results\run2.err.log')
Log "retry run exited with code $LASTEXITCODE"
