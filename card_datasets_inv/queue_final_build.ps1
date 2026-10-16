# Waits for the LARGE retry (its waiter process) to exit, fixes the Decimal bug, then re-runs the notebook to
# build the outputs. Nothing is left to probe by then, so this only re-reads metadata and assembles results.
param([int]$WaitPid = 10824)

$dir = $PSScriptRoot
$py = 'C:\Users\fintan.creedon\code\exploration\.venv\Scripts\python.exe'
$jupyter = 'C:\Users\fintan.creedon\code\exploration\.venv\Scripts\jupyter.exe'
$log = Join-Path $dir 'results\queue.log'

function Log($m) { "$(Get-Date -Format s) $m" | Out-File -FilePath $log -Append -Encoding utf8 }

Log "final build: waiting for PID $WaitPid"
Wait-Process -Id $WaitPid -ErrorAction SilentlyContinue
Log "PID $WaitPid exited; applying Decimal fix"
& $py (Join-Path $dir 'patch_numeric_sizes.py') 2>&1 | ForEach-Object { Log $_ }

Remove-Item Env:CARD_INV_RETRY_FAILED -ErrorAction SilentlyContinue
$env:CARD_INV_WAREHOUSE = 'LARGE'   # in case a December count is still missing
$env:CARD_INV_DEC_TIMEOUT_S = '3600'
Log "starting final build run"
& $jupyter nbconvert --to notebook --execute card_datasets_inventory.ipynb --inplace `
    --ExecutePreprocessor.timeout=-1 --ExecutePreprocessor.kernel_name=exploration `
    1>> (Join-Path $dir 'results\run3.log') 2>> (Join-Path $dir 'results\run3.err.log')
Log "final build exited with code $LASTEXITCODE"
