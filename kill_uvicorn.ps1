# Kill ALL existing uvicorn processes
Write-Host "=== Killing existing uvicorn processes ===" -ForegroundColor Yellow

$to_kill = @(62188, 66176)
foreach ($pid in $to_kill) {
    try {
        $proc = Get-Process -Id $pid -ErrorAction Stop
        Write-Host "Stopping PID $pid ( $($proc.Path) )"
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "  -> Stopped"
    } catch {
        Write-Host "  -> Already gone or cannot stop"
    }
}

# Also kill any other python processes that might be uvicorn
Write-Host ""
Write-Host "=== Remaining Python processes ==="
Get-Process python | ForEach-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction Stop | Select-Object -ExpandProperty CommandLine)
        Write-Host "PID $($_.Id): $cmd"
    } catch {
        Write-Host "PID $($_.Id): (unknown)"
    }
}